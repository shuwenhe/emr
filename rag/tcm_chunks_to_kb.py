"""
tcm_chunks_to_kb.py
====================
Stage 3 of the TCM corpus pipeline: chunks JSONL → FAISS knowledge base.

Reads the chunks produced by docs_to_chunks_jsonl.py (or the one-click
run_auto_dedup_chunk_pipeline.py), embeds every chunk, and writes a
knowledge base directory that is fully compatible with kb_loader.py /
the `make kb-build` KB format:

    <out-dir>/
        current  -> versions/<kb_version>/     (symlink)
        versions/
            <kb_version>/
                index.faiss
                chunks.jsonl
                manifest.json
                build_log.json

Usage
-----
    python rag/tcm_chunks_to_kb.py \\
        --chunks-input  rag/dataset/TCM_pretrain_book_chunks.jsonl \\
        --out-dir       rag/kb \\
        --provider      ollama \\
        --embed-model   bge-m3:latest \\
        --batch-size    32

    # test with only the first 500 chunks:
    python rag/tcm_chunks_to_kb.py \\
        --chunks-input  rag/dataset/TCM_pretrain_book_chunks.jsonl \\
        --out-dir       /tmp/kb_tcm_test \\
        --limit-chunks  500
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import os
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np
import faiss
from tqdm import tqdm

# Allow running as `python rag/tcm_chunks_to_kb.py` from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag.embeddings import build_embeddings
from rag.kb_utils import sha1_text
from rag.kb_builder import (
    GoEmbedder,
    _activate_version,
    _embed_batch_with_fallback,
    _embed_documents_with_retry,
    _env_flag,
    _find_go_embedder,
)
from rag.schemas import ChunkRecord, Manifest


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _iter_jsonl(path: str, limit: Optional[int] = None) -> Iterator[dict]:
    count = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
            count += 1
            if limit is not None and count >= limit:
                return


def _count_lines(path: str) -> int:
    n = 0
    with open(path, "rb") as fh:
        for _ in fh:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Field mapping: our chunks JSONL → ChunkRecord
# ---------------------------------------------------------------------------

def _to_chunk_record(row: dict, chunk_index: int) -> ChunkRecord:
    """Convert one row from docs_to_chunks_jsonl.py output to a ChunkRecord."""
    # `id` is the unique SHA1 for this chunk; `chunk_id` is an int (per-doc index)
    chunk_id = row.get("id") or sha1_text(row["text"])
    return ChunkRecord(
        vector_id=-1,                                # assigned later
        chunk_id=chunk_id,
        file_path=row.get("source", "tcm_corpus"),  # original corpus source name
        title_path=None,                            # TCM plain-text has no heading tree
        chunk_type=row.get("record_type", "tcm_pretrain_web_text"),
        chunk_index=chunk_index,
        doc_hash=row.get("doc_text_sha1") or sha1_text(row.get("doc_id", "")),
        text_for_embedding=row["text"],
        excerpt_markdown=row["text"],
    )


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------

def _iter_batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


@dataclass
class EmbedMetrics:
    backend: str
    requested_chunks: int
    batch_size: int
    batch_count: int = 0
    failed_batches: int = 0
    kept_chunks: int = 0
    failed_chunks: int = 0
    total_batch_seconds: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        avg_batch_ms = 0.0
        if self.batch_count > 0:
            avg_batch_ms = (self.total_batch_seconds / self.batch_count) * 1000
        return {
            "backend": self.backend,
            "requested_chunks": self.requested_chunks,
            "batch_size": self.batch_size,
            "batch_count": self.batch_count,
            "failed_batches": self.failed_batches,
            "kept_chunks": self.kept_chunks,
            "failed_chunks": self.failed_chunks,
            "total_batch_seconds": round(self.total_batch_seconds, 4),
            "avg_batch_ms": round(avg_batch_ms, 2),
        }


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_kb_from_chunks(
    chunks_input: str,
    out_dir: str,
    provider: str,
    embed_model: str,
    base_url: Optional[str],
    api_key: Optional[str],
    batch_size: int = 32,
    limit_chunks: Optional[int] = None,
) -> Manifest:
    start_time = time.perf_counter()

    # ---- count lines for progress bar ----
    print(f"Counting chunks in {chunks_input} …")
    total_lines = _count_lines(chunks_input)
    if limit_chunks is not None:
        total_lines = min(total_lines, limit_chunks)
    print(f"  → {total_lines:,} chunks to embed")

    # ---- read all chunk records ----
    print("Loading chunk records …")
    records: List[ChunkRecord] = []
    with tqdm(total=total_lines, desc="Reading chunks", unit="chunk") as pbar:
        for idx, row in enumerate(_iter_jsonl(chunks_input, limit=limit_chunks)):
            records.append(_to_chunk_record(row, chunk_index=idx))
            pbar.update(1)

    if not records:
        raise RuntimeError("No chunks found in input file.")

    # ---- embed ----
    print(f"Embedding {len(records):,} chunks via provider={provider!r} model={embed_model!r} …")
    use_go_embedder = _env_flag("RAG_USE_GO_EMBEDDER", default=True)
    go_bin = _find_go_embedder() if use_go_embedder else None
    go_embed_concurrency = max(1, int(os.getenv("RAG_GO_EMBED_CONCURRENCY", "8")))
    if go_bin:
        embeddings_fn = GoEmbedder(
            binary=go_bin,
            provider=provider,
            model=embed_model,
            base_url=base_url,
            api_key=api_key,
            concurrency=go_embed_concurrency,
        )
    else:
        if use_go_embedder:
            tqdm.write("[WARN] RAG_USE_GO_EMBEDDER=1 but go_embedder binary not found; fallback to python backend")
        embeddings_fn = build_embeddings(provider, embed_model, base_url=base_url, api_key=api_key)

    backend_name = "go-concurrent" if isinstance(embeddings_fn, GoEmbedder) else "python"
    metrics = EmbedMetrics(backend=backend_name, requested_chunks=len(records), batch_size=batch_size)
    metrics_every = max(1, int(os.getenv("RAG_EMBED_METRICS_EVERY", "20")))

    vectors: List[List[float]] = []
    kept_records: List[ChunkRecord] = []
    embedding_failed: List[Dict[str, str]] = []

    try:
        with tqdm(total=len(records), desc="Embedding", unit="chunk") as pbar:
            if isinstance(embeddings_fn, GoEmbedder):
                pipeline_workers = max(
                    1,
                    int(os.getenv("RAG_EMBED_PIPELINE_WORKERS", os.getenv("EMBED_PIPELINE_WORKERS", "8"))),
                )
                max_inflight = max(
                    1,
                    int(
                        os.getenv(
                            "RAG_EMBED_PIPELINE_INFLIGHT",
                            os.getenv("EMBED_PIPELINE_INFLIGHT", str(pipeline_workers * 2)),
                        )
                    ),
                )
                batch_iter = iter(_iter_batches(records, batch_size))
                in_flight = {}

                with ThreadPoolExecutor(max_workers=pipeline_workers) as executor:
                    def _submit_next() -> bool:
                        try:
                            next_batch = next(batch_iter)
                        except StopIteration:
                            return False
                        future = executor.submit(_embed_batch_with_fallback, embeddings_fn, next_batch)
                        in_flight[future] = (len(next_batch), time.perf_counter())
                        return True

                    while len(in_flight) < max_inflight and _submit_next():
                        pass

                    while in_flight:
                        done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                        for future in done:
                            input_size, batch_start = in_flight.pop(future)
                            elapsed = time.perf_counter() - batch_start
                            batch_kept, batch_vectors, batch_failed, warns = future.result()
                            for msg in warns:
                                tqdm.write(msg)
                            kept_records.extend(batch_kept)
                            vectors.extend(batch_vectors)
                            embedding_failed.extend(batch_failed)
                            metrics.batch_count += 1
                            metrics.total_batch_seconds += elapsed
                            metrics.kept_chunks += len(batch_kept)
                            metrics.failed_chunks += len(batch_failed)
                            if batch_failed:
                                metrics.failed_batches += 1
                            if metrics.batch_count % metrics_every == 0:
                                tqdm.write(
                                    "[EMBED_METRIC] "
                                    f"backend={backend_name} batch={metrics.batch_count} "
                                    f"elapsed_ms={elapsed * 1000:.1f} "
                                    f"kept={len(batch_kept)} failed={len(batch_failed)}"
                                )
                            pbar.update(input_size)

                        while len(in_flight) < max_inflight and _submit_next():
                            pass
            else:
                for batch in _iter_batches(records, batch_size):
                    batch_start = time.perf_counter()
                    batch_kept, batch_vectors, batch_failed, warns = _embed_batch_with_fallback(
                        embeddings_fn,
                        batch,
                    )
                    elapsed = time.perf_counter() - batch_start
                    for msg in warns:
                        tqdm.write(msg)
                    kept_records.extend(batch_kept)
                    vectors.extend(batch_vectors)
                    embedding_failed.extend(batch_failed)
                    metrics.batch_count += 1
                    metrics.total_batch_seconds += elapsed
                    metrics.kept_chunks += len(batch_kept)
                    metrics.failed_chunks += len(batch_failed)
                    if batch_failed:
                        metrics.failed_batches += 1
                    if metrics.batch_count % metrics_every == 0:
                        tqdm.write(
                            "[EMBED_METRIC] "
                            f"backend={backend_name} batch={metrics.batch_count} "
                            f"elapsed_ms={elapsed * 1000:.1f} "
                            f"kept={len(batch_kept)} failed={len(batch_failed)}"
                        )
                    pbar.update(len(batch))
    finally:
        if isinstance(embeddings_fn, GoEmbedder):
            embeddings_fn.close()

    tqdm.write(f"[EMBED_SUMMARY] {json.dumps(metrics.to_dict(), ensure_ascii=True)}")

    records = kept_records
    if embedding_failed:
        tqdm.write(f"[WARN] {len(embedding_failed)} chunk(s) skipped due to embedding errors.")

    if not vectors:
        raise RuntimeError("Embedding returned no vectors.")

    # ---- build FAISS index ----
    print("Building FAISS index (cosine / inner-product after L2-norm) …")
    vector_array = np.array(vectors, dtype="float32")
    faiss.normalize_L2(vector_array)
    dim = vector_array.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vector_array)

    for i, rec in enumerate(records):
        rec.vector_id = i

    # ---- write KB artifacts ----
    kb_version = datetime.now().strftime("%Y%m%d-%H%M%S")
    versions_dir = os.path.join(out_dir, "versions")
    version_dir = os.path.join(versions_dir, kb_version)
    os.makedirs(version_dir, exist_ok=True)

    print(f"Writing KB artifacts → {version_dir}")

    faiss.write_index(index, os.path.join(version_dir, "index.faiss"))

    with open(os.path.join(version_dir, "chunks.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.model_dump(), ensure_ascii=True))
            fh.write("\n")

    manifest = Manifest(
        kb_version=kb_version,
        source_dir=chunks_input,
        build_time=datetime.now(timezone.utc).isoformat(),
        embedding_model=embed_model,
        llm_provider_default=provider,
        faiss_metric="cosine",
        doc_count=len({r.doc_hash for r in records}),
        chunk_count=len(records),
        failed_files=[item["chunk_id"] for item in embedding_failed],
    )
    with open(os.path.join(version_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest.model_dump(), fh, ensure_ascii=False, indent=2)

    build_log = {
        "kb_version": kb_version,
        "chunks_input": chunks_input,
        "total_read": total_lines,
        "embedded": len(records),
        "embedding_failed": embedding_failed,
        "embedding_metrics": metrics.to_dict(),
    }
    with open(os.path.join(version_dir, "build_log.json"), "w", encoding="utf-8") as fh:
        json.dump(build_log, fh, ensure_ascii=False, indent=2)

    print("Activating KB version (atomic symlink switch) …")
    _activate_version(out_dir, version_dir)

    elapsed = time.perf_counter() - start_time
    print(
        f"Done. chunks={len(records):,}, dim={dim}, "
        f"duration={elapsed:.1f}s, version={kb_version}"
    )
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a FAISS knowledge base from TCM chunks JSONL (Stage 3 of TCM pipeline).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--chunks-input",
        required=True,
        help="Path to chunks JSONL produced by docs_to_chunks_jsonl.py (or run_auto_dedup_chunk_pipeline.py).",
    )
    p.add_argument(
        "--out-dir",
        default="rag/kb",
        help="Root output directory for the knowledge base.",
    )
    p.add_argument(
        "--provider",
        default=os.getenv("PROVIDER", "ollama"),
        choices=["ollama", "openai-compatible"],
        help="Embedding provider.",
    )
    p.add_argument(
        "--embed-model",
        default=os.getenv("EMBED_MODEL", "bge-m3:latest"),
        help="Embedding model name.",
    )
    p.add_argument(
        "--base-url",
        default=os.getenv("OLLAMA_BASE_URL", os.getenv("OPENAI_BASE_URL")),
        help="API base URL (Ollama or OpenAI-compatible endpoint).",
    )
    p.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="API key (for openai-compatible provider).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of chunks per embedding request.",
    )
    p.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N chunks (useful for smoke-tests).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    build_kb_from_chunks(
        chunks_input=args.chunks_input,
        out_dir=args.out_dir,
        provider=args.provider,
        embed_model=args.embed_model,
        base_url=args.base_url or None,
        api_key=args.api_key or None,
        batch_size=args.batch_size,
        limit_chunks=args.limit_chunks,
    )


if __name__ == "__main__":
    main()
