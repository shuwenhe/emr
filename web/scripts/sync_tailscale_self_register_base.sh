#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

TAILSCALE_PORT="${TAILSCALE_PORT:-3000}"
TAILSCALE_PROTOCOL="${TAILSCALE_PROTOCOL:-http}"
TAILSCALE_HOST="${TAILSCALE_HOST:-}"

if [[ -z "$TAILSCALE_HOST" ]]; then
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "[ERROR] tailscale command not found. Install Tailscale or set TAILSCALE_HOST manually."
    exit 1
  fi

  TAILSCALE_HOST="$(tailscale ip -4 | head -n 1 | tr -d '[:space:]')"
fi

if [[ -z "$TAILSCALE_HOST" ]]; then
  echo "[ERROR] Failed to determine Tailscale host."
  exit 1
fi

WEB_BASE="${TAILSCALE_PROTOCOL}://${TAILSCALE_HOST}:${TAILSCALE_PORT}"
printf '%s\n' "$WEB_BASE" > "$URL_FILE"
: > "$LEGACY_URL_FILE"

echo "[OK] Wrote self-register base: $WEB_BASE"
echo "[OK] File: $URL_FILE"
echo "[TIP] Open /patients -> 微信扫码登记 to use the updated QR code."