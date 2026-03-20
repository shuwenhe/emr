#!/usr/bin/env python3
"""Generate knowledge_base.json from knowledge_base.jsonl.

JSONL is treated as the only editable source of truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_kb_jsonl import validate_jsonl_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate knowledge_base.json from knowledge_base.jsonl")
    parser.add_argument(
        "--input-jsonl",
        default="./rag/kb/knowledge_base.jsonl",
        help="Input JSONL path (default: ./rag/kb/knowledge_base.jsonl)",
    )
    parser.add_argument(
        "--output-json",
        default="./rag/kb/knowledge_base.json",
        help="Output JSON path (default: ./rag/kb/knowledge_base.json)",
    )
    parser.add_argument(
        "--sort-by-id",
        action="store_true",
        help="Sort rows by id before writing JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_jsonl).resolve()
    output_path = Path(args.output_json).resolve()

    if not input_path.exists() or not input_path.is_file():
        print(f"[ERROR] Input JSONL not found: {input_path}")
        return 2

    rows, errors = validate_jsonl_file(input_path)
    if errors:
        print(f"[ERROR] Cannot generate JSON because validation failed: {input_path}")
        for err in errors:
            print(f"  - {err}")
        return 1

    if args.sort_by_id:
        rows = sorted(rows, key=lambda item: str(item.get("id") or ""))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, ensure_ascii=False, indent=2)
    if payload:
        payload += "\n"

    if output_path.exists():
        old = output_path.read_text(encoding="utf-8")
        if old == payload:
            print(
                f"[OK] JSON already up to date: input={input_path} output={output_path} rows={len(rows)}"
            )
            return 0

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(output_path)

    print(
        f"[OK] Generated JSON from JSONL: input={input_path} output={output_path} rows={len(rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
