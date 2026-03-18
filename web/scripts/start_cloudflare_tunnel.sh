#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="$WEB_DIR/.tools"
LOG_DIR="$WEB_DIR/.tunnel"
LOG_FILE="$LOG_DIR/cloudflared.log"
PID_FILE="$LOG_DIR/cloudflared.pid"
URL_FILE="$WEB_DIR/public/tunnel-url.txt"

mkdir -p "$TOOLS_DIR" "$LOG_DIR"

find_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return
  fi

  local local_bin="$TOOLS_DIR/cloudflared"
  if [[ -x "$local_bin" ]]; then
    echo "$local_bin"
    return
  fi

  echo "[INFO] cloudflared not found, downloading local binary..." >&2
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o "$local_bin"
  chmod +x "$local_bin"
  echo "$local_bin"
}

CLOUDFLARED_BIN="$(find_cloudflared)"

# Use local HTTP proxy if Cloudflare API is not directly reachable.
HTTPS_PROXY="${HTTPS_PROXY:-}"
if [[ -z "$HTTPS_PROXY" ]]; then
  for proxy_candidate in "http://127.0.0.1:7890" "http://127.0.0.1:1080"; do
    if curl -sf --proxy "$proxy_candidate" --max-time 4 https://api.trycloudflare.com -o /dev/null 2>/dev/null; then
      HTTPS_PROXY="$proxy_candidate"
      HTTP_PROXY="$proxy_candidate"
      echo "[INFO] Using proxy: $HTTPS_PROXY"
      break
    fi
  done
fi
export HTTPS_PROXY HTTP_PROXY

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
    echo "[INFO] Stopping existing cloudflared process: $old_pid"
    kill "$old_pid" || true
    sleep 1
  fi
fi

: > "$LOG_FILE"
: > "$URL_FILE"

"$CLOUDFLARED_BIN" tunnel --url http://127.0.0.1:3000 >"$LOG_FILE" 2>&1 &
new_pid=$!
echo "$new_pid" > "$PID_FILE"

echo "[INFO] cloudflared started (pid=$new_pid), waiting for public URL..."

public_url=""
for _ in $(seq 1 60); do
  if [[ -f "$LOG_FILE" ]]; then
    # shellcheck disable=SC2002
    public_url="$(cat "$LOG_FILE" | grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' | grep -v 'api\.trycloudflare\.com' | head -n 1 || true)"
  fi
  if [[ -n "$public_url" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "$public_url" ]]; then
  echo "[ERROR] Failed to obtain Cloudflare tunnel URL."
  echo "[ERROR] Check log: $LOG_FILE"
  exit 1
fi

echo "$public_url" > "$URL_FILE"

echo "[OK] Tunnel URL: $public_url"
echo "[OK] Written to: $URL_FILE"
echo "[TIP] Open /patients -> 微信扫码登记, it will auto-read this URL."
