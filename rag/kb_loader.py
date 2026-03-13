from __future__ import annotations

import json
import logging
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
    skipped_lines = 0
    with open(chunks_path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = ChunkRecord.model_validate_json(line)
            except Exception as exc:  # noqa: BLE001
                skipped_lines += 1
                logging.warning(
                    "skipping malformed chunk row: kb_path=%s line=%s error=%s",
                    kb_path,
                    line_no,
                    exc,
                )
                continue
            chunks[record.vector_id] = record

    if not chunks:
        raise RuntimeError(f"No valid chunk rows loaded from {chunks_path}")
    if skipped_lines > 0:
        logging.warning(
            "loaded KB with skipped malformed rows: kb_path=%s skipped=%s loaded=%s index_ntotal=%s",
            kb_path,
            skipped_lines,
            len(chunks),
            getattr(index, "ntotal", "?"),
        )

    manifest = None
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = Manifest.model_validate(json.load(handle))

    return KnowledgeBase(index=index, chunks=chunks, manifest=manifest)
