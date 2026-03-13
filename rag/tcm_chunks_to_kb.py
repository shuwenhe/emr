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
import json
import os
import shutil
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
    _activate_partial_link,
    _append_checkpoint_rows,
    _checkpoint_signature,
    _embed_batch_with_fallback,
    _env_flag,
    _find_go_embedder,
    _load_embedding_checkpoint,
    _start_resource_monitor,
    _write_checkpoint_state,
    _write_partial_snapshot_from_index,
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
    stop_resource_monitor = lambda: None
    embeddings_fn = None
    chunks_tmp_path = ""
    chunks_handle = None

    # ---- count lines for progress bar ----
    print(f"Counting chunks in {chunks_input} …")
    total_lines = _count_lines(chunks_input)
    if limit_chunks is not None:
        total_lines = min(total_lines, limit_chunks)
    print(f"  → {total_lines:,} chunks to embed")

    kb_version = datetime.now().strftime("%Y%m%d-%H%M%S")
    versions_dir = os.path.join(out_dir, "versions")
    version_dir = os.path.join(versions_dir, kb_version)
    os.makedirs(version_dir, exist_ok=True)
    chunks_tmp_path = os.path.join(version_dir, "chunks.jsonl.tmp")

    resume_enabled = _env_flag("RAG_EMBED_RESUME", default=True)
    checkpoint_every = max(1, int(os.getenv("RAG_CHECKPOINT_EVERY_BATCHES", "20")))
    partial_every = max(0, int(os.getenv("RAG_PARTIAL_KB_EVERY_BATCHES", "50")))
    checkpoint_dir = os.path.join(out_dir, ".kb_checkpoint_tcm")
    checkpoint_signature = _checkpoint_signature(
        {
            "chunks_input": chunks_input,
            "provider": provider,
            "embed_model": embed_model,
            "batch_size": batch_size,
            "limit_chunks": limit_chunks,
        }
    )
    checkpoint_embedded_path = os.path.join(checkpoint_dir, "embedded.jsonl")
    checkpoint_failed_path = os.path.join(checkpoint_dir, "failed.jsonl")

    resumed_map: Dict[str, Tuple[ChunkRecord, List[float]]] = {}
    resumed_failed: List[Dict[str, str]] = []
    resumed_loaded = 0
    if resume_enabled:
        resumed_map, resumed_failed, resumed_loaded = _load_embedding_checkpoint(
            checkpoint_dir,
            checkpoint_signature,
        )

    pending_records: List[ChunkRecord] = []
    embedding_failed: List[Dict[str, str]] = list(resumed_failed)
    index: Optional[faiss.Index] = None
    next_vector_id = 0
    total_discovered = 0
    resumed_applied = 0
    seen_doc_hashes: set[str] = set()

    chunks_handle = open(chunks_tmp_path, "w", encoding="utf-8")

    def _append_embedded_record(record: ChunkRecord, vector: List[float]) -> None:
        nonlocal index, next_vector_id
        vec = np.asarray(vector, dtype="float32")
        if vec.ndim != 1 or vec.size == 0:
            raise RuntimeError("invalid embedding vector shape")
        arr = vec.reshape(1, -1)
        faiss.normalize_L2(arr)
        if index is None:
            index = faiss.IndexFlatIP(arr.shape[1])
        elif index.d != arr.shape[1]:
            raise RuntimeError(f"embedding dim mismatch: expected {index.d}, got {arr.shape[1]}")
        index.add(arr)

        record.vector_id = next_vector_id
        next_vector_id += 1
        chunks_handle.write(json.dumps(record.model_dump(), ensure_ascii=True))
        chunks_handle.write("\n")

    if resumed_loaded > 0:
        tqdm.write(f"[RESUME] checkpoint entries loaded={resumed_loaded}")
    elif resume_enabled:
        _write_checkpoint_state(
            checkpoint_dir,
            checkpoint_signature,
            {
                "kb_version": kb_version,
                "phase": "embedding",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_chunks": 0,
                "embedded_chunks": 0,
                "failed_chunks": len(embedding_failed),
            },
        )

    # ---- stream parse + embed ----
    stop_resource_monitor = _start_resource_monitor("kb-build-tcm")
    print(f"Streaming embed chunks via provider={provider!r} model={embed_model!r} …")
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
    metrics = EmbedMetrics(backend=backend_name, requested_chunks=0, batch_size=batch_size)
    metrics_every = max(1, int(os.getenv("RAG_EMBED_METRICS_EVERY", "20")))

    try:
        with tqdm(total=total_lines, desc="Streaming parse+embed", unit="chunk") as pbar:

            def _after_batch(
                batch_kept: List[ChunkRecord],
                batch_vectors: List[List[float]],
                batch_failed: List[Dict[str, str]],
            ) -> None:
                nonlocal embedding_failed
                next_batch_count = metrics.batch_count + 1
                for rec, vec in zip(batch_kept, batch_vectors):
                    _append_embedded_record(rec, vec)
                embedding_failed.extend(batch_failed)
                metrics.requested_chunks = total_discovered
                if not resume_enabled:
                    return

                embed_rows = [
                    {"chunk_id": rec.chunk_id, "record": rec.model_dump(), "vector": vec}
                    for rec, vec in zip(batch_kept, batch_vectors)
                ]
                _append_checkpoint_rows(checkpoint_embedded_path, embed_rows)
                failed_rows = [
                    {
                        "chunk_id": str(item.get("chunk_id") or ""),
                        "file_path": str(item.get("file_path") or ""),
                        "reason": str(item.get("reason") or ""),
                    }
                    for item in batch_failed
                ]
                _append_checkpoint_rows(checkpoint_failed_path, failed_rows)
                if next_batch_count % checkpoint_every == 0:
                    _write_checkpoint_state(
                        checkpoint_dir,
                        checkpoint_signature,
                        {
                            "kb_version": kb_version,
                            "phase": "embedding",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "total_chunks": total_discovered,
                            "embedded_chunks": next_vector_id,
                            "failed_chunks": len(embedding_failed),
                        },
                    )

                if partial_every > 0 and next_batch_count % partial_every == 0 and next_vector_id > 0:
                    chunks_handle.flush()
                    os.fsync(chunks_handle.fileno())
                    partial_dir = os.path.join(version_dir, "partial")
                    _write_partial_snapshot_from_index(
                        partial_dir=partial_dir,
                        index=index,
                        chunks_src_path=chunks_tmp_path,
                        kb_version=kb_version,
                        source_dir=chunks_input,
                        embed_model=embed_model,
                        provider=provider,
                        failed_items=embedding_failed,
                        chunk_count=next_vector_id,
                    )
                    _activate_partial_link(out_dir, partial_dir)

            def _process_batch(batch: List[ChunkRecord]) -> None:
                if not batch:
                    return
                batch_start = time.perf_counter()
                batch_kept, batch_vectors, batch_failed, warns = _embed_batch_with_fallback(
                    embeddings_fn,
                    batch,
                )
                elapsed = time.perf_counter() - batch_start
                for msg in warns:
                    tqdm.write(msg)
                _after_batch(batch_kept, batch_vectors, batch_failed)
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

            for idx, row in enumerate(_iter_jsonl(chunks_input, limit=limit_chunks)):
                record = _to_chunk_record(row, chunk_index=idx)
                total_discovered += 1
                seen_doc_hashes.add(record.doc_hash)

                resumed = resumed_map.get(record.chunk_id)
                if resumed:
                    resumed_record, resumed_vector = resumed
                    record.text_for_embedding = resumed_record.text_for_embedding
                    _append_embedded_record(record, resumed_vector)
                    resumed_applied += 1
                    pbar.update(1)
                    continue

                pending_records.append(record)
                if len(pending_records) >= batch_size:
                    _process_batch(pending_records)
                    pending_records = []

            if pending_records:
                _process_batch(pending_records)

        metrics.requested_chunks = total_discovered
        if resumed_applied > 0:
            tqdm.write(f"[RESUME] applied {resumed_applied} chunk(s) from checkpoint during streaming parse")
        if total_discovered == 0:
            raise RuntimeError("No chunks found in input file.")

        if resume_enabled:
            _write_checkpoint_state(
                checkpoint_dir,
                checkpoint_signature,
                {
                    "kb_version": kb_version,
                    "phase": "embedding_finished",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "total_chunks": total_discovered,
                    "embedded_chunks": next_vector_id,
                    "failed_chunks": len(embedding_failed),
                },
            )
    finally:
        if chunks_handle is not None:
            try:
                if not chunks_handle.closed:
                    chunks_handle.close()
            except Exception:
                pass
        if chunks_tmp_path and os.path.exists(chunks_tmp_path):
            try:
                os.remove(chunks_tmp_path)
            except Exception:
                pass
        if isinstance(embeddings_fn, GoEmbedder):
            embeddings_fn.close()
        stop_resource_monitor()

    tqdm.write(f"[EMBED_SUMMARY] {json.dumps(metrics.to_dict(), ensure_ascii=True)}")
    if embedding_failed:
        tqdm.write(f"[WARN] {len(embedding_failed)} chunk(s) skipped due to embedding errors.")

    if index is None or next_vector_id == 0:
        raise RuntimeError("Embedding returned no vectors.")

    chunks_handle.flush()
    os.fsync(chunks_handle.fileno())
    chunks_handle.close()

    # ---- build FAISS index ----
    print("Finalizing FAISS index (cosine / inner-product after L2-norm) …")
    dim = index.d

    # ---- write KB artifacts ----
    print(f"Writing KB artifacts → {version_dir}")

    faiss.write_index(index, os.path.join(version_dir, "index.faiss"))

    os.replace(chunks_tmp_path, os.path.join(version_dir, "chunks.jsonl"))

    manifest = Manifest(
        kb_version=kb_version,
        source_dir=chunks_input,
        build_time=datetime.now(timezone.utc).isoformat(),
        embedding_model=embed_model,
        llm_provider_default=provider,
        faiss_metric="cosine",
        doc_count=len(seen_doc_hashes),
        chunk_count=next_vector_id,
        failed_files=[str(item.get("chunk_id") or "") for item in embedding_failed],
    )
    with open(os.path.join(version_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest.model_dump(), fh, ensure_ascii=False, indent=2)

    build_log = {
        "kb_version": kb_version,
        "chunks_input": chunks_input,
        "total_read": total_discovered,
        "target_read": total_lines,
        "embedded": next_vector_id,
        "embedding_failed": embedding_failed,
        "embedding_metrics": metrics.to_dict(),
        "resume_enabled": resume_enabled,
        "checkpoint_every_batches": checkpoint_every,
        "partial_snapshot_every_batches": partial_every,
        "resumed_chunks": resumed_applied,
        "resumed_checkpoint_entries_loaded": resumed_loaded,
    }
    with open(os.path.join(version_dir, "build_log.json"), "w", encoding="utf-8") as fh:
        json.dump(build_log, fh, ensure_ascii=False, indent=2)

    print("Activating KB version (atomic symlink switch) …")
    _activate_version(out_dir, version_dir)
    if resume_enabled and os.path.exists(checkpoint_dir):
        shutil.rmtree(checkpoint_dir, ignore_errors=True)

    elapsed = time.perf_counter() - start_time
    print(
        f"Done. chunks={next_vector_id:,}, dim={dim}, "
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
