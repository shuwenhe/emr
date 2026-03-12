#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from hashlib import sha1
from typing import Dict, Generator, Iterable, List, Optional

try:
    from rag.kb_utils import chunk_text, clean_text
except ImportError:
    from kb_utils import chunk_text, clean_text  # type: ignore[no-redef]


def iter_json_array_objects(file_path: str) -> Generator[Dict, None, None]:
    """Stream JSON objects from a top-level JSON array without loading full file."""
    decoder = json.JSONDecoder()
    with open(file_path, "r", encoding="utf-8") as f:
        buffer = ""
        in_array = False
        eof = False

        while True:
            chunk = f.read(1 << 20)
            if chunk:
                buffer += chunk
            else:
                eof = True

            if not in_array:
                stripped = buffer.lstrip()
                if not stripped:
                    if eof:
                        return
                    continue
                if stripped[0] != "[":
                    raise ValueError("Input JSON must be a top-level array")
                buffer = stripped[1:]
                in_array = True

            while True:
                stripped = buffer.lstrip()
                if not stripped:
                    break
                if stripped[0] == "]":
                    return
                if stripped[0] == ",":
                    buffer = stripped[1:]
                    continue

                try:
                    obj, idx = decoder.raw_decode(stripped)
                except json.JSONDecodeError:
                    if eof:
                        raise
                    break

                yield obj
                buffer = stripped[idx:]

            if eof:
                break


def extract_text_items(record: Dict) -> Iterable[str]:
    content = record.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                yield text


def build_chunk_id(doc_id: str, chunk_index: int, text: str) -> str:
    raw = f"{doc_id}:{chunk_index}:{text[:64]}"
    return sha1(raw.encode("utf-8")).hexdigest()


def convert(
    input_path: str,
    output_path: str,
    chunk_size: int,
    overlap: int,
    min_len: int,
    limit_records: Optional[int],
    keep_url: bool,
) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    processed_records = 0
    total_chunks = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for rec_idx, record in enumerate(iter_json_array_objects(input_path)):
            if limit_records is not None and processed_records >= limit_records:
                break

            record_type = record.get("type", "") if isinstance(record, dict) else ""

            for text_idx, raw_text in enumerate(extract_text_items(record)):
                cleaned = clean_text(raw_text, keep_url=keep_url)
                if len(cleaned) < min_len:
                    continue

                chunks = chunk_text(cleaned, chunk_size=chunk_size, overlap=overlap)
                doc_id = f"rec{rec_idx}_txt{text_idx}"
                for i, chunk in enumerate(chunks):
                    if len(chunk) < min_len:
                        continue
                    row = {
                        "id": build_chunk_id(doc_id, i, chunk),
                        "doc_id": doc_id,
                        "chunk_id": i,
                        "source": os.path.abspath(input_path),
                        "record_type": record_type,
                        "text": chunk,
                        "char_len": len(chunk),
                    }
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    total_chunks += 1

            processed_records += 1
            if processed_records % 10000 == 0:
                print(
                    f"processed_records={processed_records} total_chunks={total_chunks}",
                    file=sys.stderr,
                    flush=True,
                )

    print(
        f"done: input={input_path} output={output_path} records={processed_records} chunks={total_chunks}",
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean and chunk TCM pretrain corpus JSON into JSONL chunks."
    )
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output JSONL file path")
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
        help="Drop cleaned texts/chunks shorter than this length (default: 80)",
    )
    parser.add_argument(
        "--limit-records",
        type=int,
        default=None,
        help="Process only first N records for quick test",
    )
    parser.add_argument(
        "--keep-url",
        action="store_true",
        help="Keep URLs in text (default removes URLs)",
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
        limit_records=args.limit_records,
        keep_url=args.keep_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
