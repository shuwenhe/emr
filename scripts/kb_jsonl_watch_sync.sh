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

run_sync() {
  if KB_PY="$KB_PY" KB_JSON_PATH="$KB_JSON_PATH" KB_JSONL_PATH="$KB_JSONL_PATH" \
    bash "$REPO_DIR/scripts/sync_kb_json_to_jsonl.sh" >/dev/null 2>&1; then
    log "synced json <-> jsonl"
  else
    log "sync failed; keep watching"
  fi
}

watch_with_inotify() {
  local watch_dir
  local json_name
  local jsonl_name
  watch_dir="$(dirname "$KB_JSONL_PATH")"
  json_name="$(basename "$KB_JSON_PATH")"
  jsonl_name="$(basename "$KB_JSONL_PATH")"

  log "watch mode=inotify path=$watch_dir files=$jsonl_name,$json_name"
  run_sync

  inotifywait -m -q \
    -e close_write -e moved_to -e create \
    --format '%f' "$watch_dir" | while read -r changed_name; do
      if [[ "$changed_name" == "$jsonl_name" || "$changed_name" == "$json_name" ]]; then
        run_sync
      fi
    done
}

watch_with_polling() {
  local last_json_sig=""
  local last_jsonl_sig=""
  local json_sig=""
  local jsonl_sig=""

  log "watch mode=polling interval=${KB_WATCH_INTERVAL}s files=$KB_JSONL_PATH,$KB_JSON_PATH"
  run_sync

  while true; do
    json_sig=""
    jsonl_sig=""
    if [[ -f "$KB_JSON_PATH" ]]; then
      json_sig="$(stat -c '%Y:%s' "$KB_JSON_PATH" 2>/dev/null || true)"
    fi
    if [[ -f "$KB_JSONL_PATH" ]]; then
      jsonl_sig="$(stat -c '%Y:%s' "$KB_JSONL_PATH" 2>/dev/null || true)"
    fi

    if [[ "$json_sig" != "$last_json_sig" || "$jsonl_sig" != "$last_jsonl_sig" ]]; then
      last_json_sig="$json_sig"
      last_jsonl_sig="$jsonl_sig"
      run_sync
    fi

    sleep "$KB_WATCH_INTERVAL"
  done
}

main() {
  log "starting KB json/jsonl watcher"
  if command -v inotifywait >/dev/null 2>&1; then
    watch_with_inotify
  else
    watch_with_polling
  fi
}

main "$@"
