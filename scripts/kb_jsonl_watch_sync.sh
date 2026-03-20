#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
KB_JSONL_PATH="${KB_JSONL_PATH:-$REPO_DIR/rag/kb/knowledge_base.jsonl}"
KB_JSON_PATH="${KB_JSON_PATH:-$REPO_DIR/rag/kb/knowledge_base.json}"
KB_WATCH_INTERVAL="${KB_WATCH_INTERVAL:-2}"
KB_PY="${KB_PY:-python3}"

log() {
  printf '[kb-watch][%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

run_export() {
  if [[ ! -f "$KB_JSONL_PATH" ]]; then
    log "skip export: source jsonl not found: $KB_JSONL_PATH"
    return 0
  fi

  if "$KB_PY" "$REPO_DIR/scripts/kb_jsonl_to_json.py" \
    --input-jsonl "$KB_JSONL_PATH" \
    --output-json "$KB_JSON_PATH" >/dev/null 2>&1; then
    log "synced jsonl -> json"
  else
    log "export failed; keep watching"
  fi
}

watch_with_inotify() {
  local watch_dir
  local target_name
  watch_dir="$(dirname "$KB_JSONL_PATH")"
  target_name="$(basename "$KB_JSONL_PATH")"

  log "watch mode=inotify path=$KB_JSONL_PATH"
  run_export

  inotifywait -m -q \
    -e close_write -e moved_to -e create \
    --format '%f' "$watch_dir" | while read -r changed_name; do
      if [[ "$changed_name" == "$target_name" ]]; then
        run_export
      fi
    done
}

watch_with_polling() {
  local last_sig=""
  local sig=""

  log "watch mode=polling interval=${KB_WATCH_INTERVAL}s path=$KB_JSONL_PATH"
  run_export

  while true; do
    if [[ -f "$KB_JSONL_PATH" ]]; then
      sig="$(stat -c '%Y:%s' "$KB_JSONL_PATH" 2>/dev/null || true)"
      if [[ -n "$sig" && "$sig" != "$last_sig" ]]; then
        last_sig="$sig"
        run_export
      fi
    fi
    sleep "$KB_WATCH_INTERVAL"
  done
}

main() {
  log "starting KB jsonl watcher"
  if command -v inotifywait >/dev/null 2>&1; then
    watch_with_inotify
  else
    watch_with_polling
  fi
}

main "$@"
