#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KB_JSON_PATH="${KB_JSON_PATH:-$REPO_DIR/rag/kb/knowledge_base.json}"
KB_JSONL_PATH="${KB_JSONL_PATH:-$REPO_DIR/rag/kb/knowledge_base.jsonl}"
KB_PY="${KB_PY:-python3}"

sync_json_to_jsonl() {
  "$KB_PY" "$REPO_DIR/scripts/kb_json_to_jsonl.py" \
    --input-json "$KB_JSON_PATH" \
    --output-jsonl "$KB_JSONL_PATH" >/dev/null 2>&1
}

sync_jsonl_to_json() {
  "$KB_PY" "$REPO_DIR/scripts/kb_jsonl_to_json.py" \
    --input-jsonl "$KB_JSONL_PATH" \
    --output-json "$KB_JSON_PATH" >/dev/null 2>&1
}

if [[ ! -f "$KB_JSON_PATH" && ! -f "$KB_JSONL_PATH" ]]; then
  exit 0
fi

if [[ -f "$KB_JSON_PATH" && ! -f "$KB_JSONL_PATH" ]]; then
  sync_json_to_jsonl
  exit 0
fi

if [[ -f "$KB_JSONL_PATH" && ! -f "$KB_JSON_PATH" ]]; then
  sync_jsonl_to_json
  exit 0
fi

json_mtime="$(stat -c '%Y' "$KB_JSON_PATH" 2>/dev/null || echo 0)"
jsonl_mtime="$(stat -c '%Y' "$KB_JSONL_PATH" 2>/dev/null || echo 0)"

if (( json_mtime > jsonl_mtime )); then
  sync_json_to_jsonl
elif (( jsonl_mtime > json_mtime )); then
  sync_jsonl_to_json
else
  # Same mtime: choose JSONL as stable tie-breaker.
  sync_jsonl_to_json
fi
