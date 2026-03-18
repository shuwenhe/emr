#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$WEB_DIR/.tunnel/cloudflared.pid"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" || true)"
  if [[ -n "${pid}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" || true
    echo "[OK] Stopped cloudflared pid=$pid"
  fi
  rm -f "$PID_FILE"
fi

: > "$URL_FILE"
: > "$LEGACY_URL_FILE"
echo "[OK] Cleared tunnel URL file: $URL_FILE"
