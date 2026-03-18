#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$REPO_DIR/.auto-git-push.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[INFO] auto git push is not running"
  exit 0
fi

pid="$(cat "$PID_FILE" || true)"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE"
  echo "[INFO] stale pid file removed"
  exit 0
fi

if kill -0 "$pid" >/dev/null 2>&1; then
  kill "$pid" || true
  sleep 1
fi

rm -f "$PID_FILE"
echo "[OK] auto git push stopped"
