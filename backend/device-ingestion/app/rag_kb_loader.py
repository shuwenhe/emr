from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class KnowledgeBase:
    index: Any
    chunks: Dict[int, Dict[str, Any]]
    manifest: Optional[Dict[str, Any]]


def load_kb(kb_path: str) -> KnowledgeBase:
    import faiss

    index_path = os.path.join(kb_path, "index.faiss")
    chunks_path = os.path.join(kb_path, "chunks.jsonl")
    manifest_path = os.path.join(kb_path, "manifest.json")

    if not os.path.exists(index_path):
        raise FileNotFoundError(f"Missing FAISS index: {index_path}")
    if not os.path.exists(chunks_path):
        raise FileNotFoundError(f"Missing chunks.jsonl: {chunks_path}")

    index = faiss.read_index(index_path)
    chunks: Dict[int, Dict[str, Any]] = {}
    with open(chunks_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            vector_id = row.get("vector_id")
            if not isinstance(vector_id, int):
                continue
            chunks[vector_id] = row

    manifest: Optional[Dict[str, Any]] = None
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except Exception:
            manifest = None

    return KnowledgeBase(index=index, chunks=chunks, manifest=manifest)
