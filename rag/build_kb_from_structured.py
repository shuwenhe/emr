#!/usr/bin/env python3
"""Build a FAISS vector KB directly from rag/kb/knowledge_base.jsonl.

This bypasses the generic TCM docx corpus and ensures the vector KB only
contains infrared-thermography-specific entries — the same source used by
the keyword fallback in llm_report.py.

Usage:
    python -m rag.build_kb_from_structured [--kb rag/kb/knowledge_base.jsonl] \
        [--out rag/kb/current_partial] [--provider ollama] [--model bge-m3:latest]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    if Path(path).suffix.lower() == ".json":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
        except Exception as exc:
            log.warning("Failed to parse JSON file %s: %s", path, exc)
            return []
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed line %d: %s", lineno, exc)
    return items


def _build_embed_text(item: Dict[str, Any]) -> str:
    """Concat title + content + tags + retrieval_hints for dense embedding."""
    parts = [
        str(item.get("title") or ""),
        str(item.get("content") or ""),
    ]
    tags = item.get("tags") or []
    if tags:
        parts.append("标签: " + " ".join(str(t) for t in tags))
    hints = item.get("retrieval_hints") or []
    if hints:
        parts.append("检索提示: " + " ".join(str(h) for h in hints))
    body_parts = item.get("body_parts") or []
    if body_parts:
        parts.append("适用部位: " + " ".join(str(b) for b in body_parts))
    risk_levels = item.get("risk_levels") or []
    if risk_levels:
        parts.append("适用风险等级: " + " ".join(str(r) for r in risk_levels))
    return "\n".join(p for p in parts if p)


def build(
    kb_jsonl: str,
    out_dir: str,
    provider: str,
    model: str,
    base_url: Optional[str],
    api_key: Optional[str],
    batch_size: int,
) -> None:
    import numpy as np
    import faiss

    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from rag.embeddings import build_embeddings

    items = _load_jsonl(kb_jsonl)
    if not items:
        log.error("No items found in %s", kb_jsonl)
        sys.exit(1)
    log.info("Loaded %d items from %s", len(items), kb_jsonl)

    embedder = build_embeddings(
        provider=provider,
        embed_model=model,
        base_url=base_url,
        api_key=api_key,
    )
    log.info("Embedding model ready: provider=%s model=%s", provider, model)

    texts = [_build_embed_text(item) for item in items]
    vectors: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        log.info("Embedding batch %d-%d / %d ...", i + 1, i + len(batch), len(texts))
        for text in batch:
            vec = embedder.embed_query(text)
            vectors.append(vec)
        time.sleep(0.05)

    arr = np.array(vectors, dtype="float32")
    faiss.normalize_L2(arr)
    dim = arr.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(arr)
    log.info("FAISS index built: ntotal=%d dim=%d", index.ntotal, dim)

    # out_dir may be a symlink pointing to a version directory; resolve it
    resolved_out = os.path.realpath(out_dir)
    os.makedirs(resolved_out, exist_ok=True)
    out_dir = resolved_out

    # Write chunks.jsonl in the format expected by kb_loader.py / ChunkRecord
    chunks_path = os.path.join(out_dir, "chunks.jsonl")
    with open(chunks_path, "w", encoding="utf-8") as f:
        for vector_id, item in enumerate(items):
            item_id = str(item.get("id") or f"item_{vector_id}")
            title = str(item.get("title") or "")
            content = str(item.get("content") or "")
            record = {
                "vector_id": vector_id,
                "chunk_id": item_id,
                "file_path": str(item.get("source") or kb_jsonl),
                "title_path": [title] if title else [],
                "chunk_type": "structured_kb",
                "chunk_index": vector_id,
                "doc_hash": _sha1(item_id + content),
                "text_for_embedding": texts[vector_id],
                "excerpt_markdown": content,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("Wrote %d chunk records to %s", len(items), chunks_path)

    index_path = os.path.join(out_dir, "index.faiss")
    faiss.write_index(index, index_path)
    log.info("Saved FAISS index to %s", index_path)

    manifest = {
        "kb_version": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "source_dir": kb_jsonl,
        "build_time": datetime.now().isoformat(),
        "embedding_model": model,
        "llm_provider_default": provider,
        "faiss_metric": "inner_product_normalized",
        "doc_count": len(items),
        "chunk_count": len(items),
        "failed_files": [],
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info("Manifest written to %s", manifest_path)
    log.info("Done. Vector KB at: %s  (%d entries)", out_dir, len(items))


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kb",
        default=str(project_root / "rag" / "kb" / "knowledge_base.json"),
        help="Path to structured knowledge_base.json (also accepts .jsonl)",
    )
    parser.add_argument(
        "--out",
        default=str(project_root / "rag" / "kb" / "current_partial"),
        help="Output directory for vector KB (index.faiss + chunks.jsonl + manifest.json)",
    )
    parser.add_argument("--provider", default=os.getenv("RAG_EMBED_PROVIDER", "ollama"))
    parser.add_argument("--model", default=os.getenv("RAG_EMBED_MODEL", "bge-m3:latest"))
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--api-key", default=os.getenv("RAG_OPENAI_API_KEY"))
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    build(
        kb_jsonl=args.kb,
        out_dir=args.out,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
