#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KB_JSON_PATH="${KB_JSON_PATH:-$REPO_DIR/rag/kb/knowledge_base.json}"
KB_JSONL_PATH="${KB_JSONL_PATH:-$REPO_DIR/rag/kb/knowledge_base.jsonl}"

if [[ ! -f "$KB_JSON_PATH" ]]; then
  exit 0
fi

python3 - "$KB_JSON_PATH" "$KB_JSONL_PATH" <<'PY'
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
jsonl_path = Path(sys.argv[2])

try:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[WARN] KB sync skipped, invalid JSON: {exc}", file=sys.stderr)
    raise SystemExit(0)

if not isinstance(payload, list):
    print("[WARN] KB sync skipped, JSON root must be an array", file=sys.stderr)
    raise SystemExit(0)

rows = []
for item in payload:
    if isinstance(item, dict):
        rows.append(json.dumps(item, ensure_ascii=False))

jsonl_text = "\n".join(rows)
if jsonl_text:
    jsonl_text += "\n"

if jsonl_path.exists():
    try:
        old_text = jsonl_path.read_text(encoding="utf-8")
        if old_text == jsonl_text:
            raise SystemExit(0)
    except Exception:
        pass

jsonl_path.parent.mkdir(parents=True, exist_ok=True)
tmp_path = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
tmp_path.write_text(jsonl_text, encoding="utf-8")
tmp_path.replace(jsonl_path)
print(f"[OK] synced KB JSON -> JSONL: {len(rows)} rows", file=sys.stderr)
PY
