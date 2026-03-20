#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KB_JSON_PATH="${KB_JSON_PATH:-$REPO_DIR/rag/kb/knowledge_base.json}"
KB_JSONL_PATH="${KB_JSONL_PATH:-$REPO_DIR/rag/kb/knowledge_base.jsonl}"

if [[ ! -f "$KB_JSONL_PATH" ]]; then
  exit 0
fi

python3 "$REPO_DIR/scripts/kb_jsonl_to_json.py" \
  --input-jsonl "$KB_JSONL_PATH" \
  --output-json "$KB_JSON_PATH" >/dev/null 2>&1 || true
