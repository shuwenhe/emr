#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WATCH_INTERVAL="${BACKEND_WATCH_INTERVAL:-2}"
BUILD_COMMAND="${BACKEND_BUILD_COMMAND:-go build ./...}"

WATCH_DIRS=(
  "cache"
  "handler"
  "model"
  "repository"
  "route"
  "service"
  "reports/go"
)

log() {
  printf '[backend-watch][%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

run_build() {
  log "开始编译: ${BUILD_COMMAND}"
  if bash -lc "$BUILD_COMMAND"; then
    log "编译成功"
  else
    log "编译失败（继续监听）"
  fi
}

snapshot_hash() {
  {
    for d in "${WATCH_DIRS[@]}"; do
      if [[ -d "$d" ]]; then
        find "$d" -type f \( -name '*.go' -o -name '*.mod' -o -name '*.sum' \) -print
      fi
    done
    [[ -f "go.mod" ]] && printf '%s\n' "go.mod"
    [[ -f "go.sum" ]] && printf '%s\n' "go.sum"
  } | sort | while IFS= read -r file; do
    [[ -n "$file" ]] || continue
    sha256sum "$file"
  done | sha256sum | awk '{print $1}'
}

watch_with_inotify() {
  local dirs=()
  local d
  for d in "${WATCH_DIRS[@]}"; do
    if [[ -d "$d" ]]; then
      dirs+=("$d")
    fi
  done
  if [[ ${#dirs[@]} -eq 0 ]]; then
    dirs=(".")
  fi

  log "监听模式: inotify"
  run_build

  inotifywait -m -r -e close_write -e create -e move -e delete --format '%w%f' "${dirs[@]}" |
    while IFS= read -r changed; do
      case "$changed" in
        *.go|*/go.mod|*/go.sum|go.mod|go.sum)
          log "检测到变更: $changed"
          run_build
          ;;
      esac
    done
}

watch_with_polling() {
  local last_hash current_hash
  log "监听模式: polling interval=${WATCH_INTERVAL}s"
  run_build
  last_hash="$(snapshot_hash)"
  while true; do
    sleep "$WATCH_INTERVAL"
    current_hash="$(snapshot_hash)"
    if [[ "$current_hash" != "$last_hash" ]]; then
      log "检测到文件变更"
      run_build
      last_hash="$current_hash"
    fi
  done
}

log "启动后端自动编译监听器"
if command -v inotifywait >/dev/null 2>&1; then
  watch_with_inotify
else
  watch_with_polling
fi
