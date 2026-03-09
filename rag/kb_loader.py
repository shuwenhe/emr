from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import faiss

from .schemas import ChunkRecord, Manifest


@dataclass
class KnowledgeBase:
    index: faiss.Index
    chunks: Dict[int, ChunkRecord]
    manifest: Optional[Manifest]


def load_kb(kb_path: str) -> KnowledgeBase:
    index_path = os.path.join(kb_path, "index.faiss")
    chunks_path = os.path.join(kb_path, "chunks.jsonl")
    manifest_path = os.path.join(kb_path, "manifest.json")
    if not os.path.exists(index_path):
        raise FileNotFoundError(f"Missing FAISS index: {index_path}")
    if not os.path.exists(chunks_path):
        raise FileNotFoundError(f"Missing chunks.jsonl: {chunks_path}")

    index = faiss.read_index(index_path)
    chunks: Dict[int, ChunkRecord] = {}
    with open(chunks_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = ChunkRecord.model_validate_json(line)
            chunks[record.vector_id] = record

    manifest = None
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = Manifest.model_validate(json.load(handle))

    return KnowledgeBase(index=index, chunks=chunks, manifest=manifest)
