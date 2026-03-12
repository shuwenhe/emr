#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from hashlib import sha1
from typing import Dict, Generator, List, Optional

try:
    from rag.kb_utils import chunk_text
except ImportError:
    from kb_utils import chunk_text  # type: ignore[no-redef]


def iter_jsonl(path: str) -> Generator[Dict, None, None]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc


def chunk_id(doc_id: str, idx: int, text: str) -> str:
    raw = f"{doc_id}:{idx}:{text[:64]}"
    return sha1(raw.encode("utf-8")).hexdigest()


def convert(
    input_path: str,
    output_path: str,
    chunk_size: int,
    overlap: int,
    min_len: int,
    limit_docs: Optional[int],
) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    doc_count = 0
    chunk_count = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for row in iter_jsonl(input_path):
            if limit_docs is not None and doc_count >= limit_docs:
                break

            text = row.get("text", "")
            if not isinstance(text, str) or len(text.strip()) < min_len:
                doc_count += 1
                continue

            doc_id = row.get("doc_id") or f"doc_{doc_count}"
            chunks = chunk_text(text.strip(), chunk_size=chunk_size, overlap=overlap)
            for i, ch in enumerate(chunks):
                if len(ch) < min_len:
                    continue

                out_row = {
                    "id": chunk_id(doc_id, i, ch),
                    "doc_id": doc_id,
                    "chunk_id": i,
                    "source": row.get("source", ""),
                    "record_type": row.get("record_type", ""),
                    "record_index": row.get("record_index"),
                    "text_index": row.get("text_index"),
                    "doc_text_sha1": row.get("text_sha1", ""),
                    "text": ch,
                    "char_len": len(ch),
                    "stage": "chunked",
                }
                out.write(json.dumps(out_row, ensure_ascii=False) + "\n")
                chunk_count += 1

            doc_count += 1
            if doc_count % 10000 == 0:
                print(
                    f"processed_docs={doc_count} chunks={chunk_count}",
                    file=sys.stderr,
                    flush=True,
                )

    print(
        f"done: input={input_path} output={output_path} docs={doc_count} chunks={chunk_count}",
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chunk normalized docs JSONL into chunk JSONL."
    )
    parser.add_argument("--input", required=True, help="Input docs JSONL path")
    parser.add_argument("--output", required=True, help="Output chunks JSONL path")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=600,
        help="Target chunk size in characters (default: 600)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=100,
        help="Overlap size in characters between adjacent chunks (default: 100)",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=80,
        help="Drop chunks shorter than this length (default: 80)",
    )
    parser.add_argument(
        "--limit-docs",
        type=int,
        default=None,
        help="Process only first N docs for quick test",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    convert(
        input_path=args.input,
        output_path=args.output,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        min_len=args.min_len,
        limit_docs=args.limit_docs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
