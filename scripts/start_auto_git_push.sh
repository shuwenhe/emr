#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$REPO_DIR/.git/.auto-git-push.pid"
LOG_FILE="$REPO_DIR/.git/.auto-git-push.log"
DAEMON_SCRIPT="$REPO_DIR/scripts/auto_git_push_daemon.sh"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
    echo "[INFO] auto git push already running (pid=$old_pid)"
    echo "[INFO] log: $LOG_FILE"
    exit 0
  fi
fi

cd "$REPO_DIR"
nohup bash "$DAEMON_SCRIPT" >> "$LOG_FILE" 2>&1 &
new_pid=$!
echo "$new_pid" > "$PID_FILE"

echo "[OK] auto git push started (pid=$new_pid)"
echo "[OK] log file: $LOG_FILE"
echo "[TIP] stop with: bash ./scripts/stop_auto_git_push.sh"
