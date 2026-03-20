#!/usr/bin/env python3
"""Generate knowledge_base.jsonl from knowledge_base.json.

Used for bidirectional sync when JSON is edited directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_kb_jsonl import validate_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate knowledge_base.jsonl from knowledge_base.json")
    parser.add_argument(
        "--input-json",
        default="./rag/kb/knowledge_base.json",
        help="Input JSON path (default: ./rag/kb/knowledge_base.json)",
    )
    parser.add_argument(
        "--output-jsonl",
        default="./rag/kb/knowledge_base.jsonl",
        help="Output JSONL path (default: ./rag/kb/knowledge_base.jsonl)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_json).resolve()
    output_path = Path(args.output_jsonl).resolve()

    if not input_path.exists() or not input_path.is_file():
        print(f"[ERROR] Input JSON not found: {input_path}")
        return 2

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Invalid JSON file: {input_path} error={exc}")
        return 1

    if not isinstance(payload, list):
        print(f"[ERROR] JSON root must be an array: {input_path}")
        return 1

    rows: list[dict] = []
    for idx, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            print(f"[ERROR] row {idx}: each item must be an object")
            return 1
        rows.append(item)

    errors = validate_rows(rows)
    if errors:
        print(f"[ERROR] Cannot generate JSONL because validation failed: {input_path}")
        for err in errors:
            print(f"  - {err}")
        return 1

    jsonl_text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if jsonl_text:
        jsonl_text += "\n"

    if output_path.exists():
        old = output_path.read_text(encoding="utf-8")
        if old == jsonl_text:
            print(
                f"[OK] JSONL already up to date: input={input_path} output={output_path} rows={len(rows)}"
            )
            return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(jsonl_text, encoding="utf-8")
    tmp_path.replace(output_path)

    print(
        f"[OK] Generated JSONL from JSON: input={input_path} output={output_path} rows={len(rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
