#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

LAN_PORT="${LAN_PORT:-3000}"
LAN_PROTOCOL="${LAN_PROTOCOL:-http}"
LAN_HOST="${LAN_HOST:-}"

detect_lan_ip() {
  if command -v ip >/dev/null 2>&1; then
    local ip_from_route
    ip_from_route="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
    if [[ -n "${ip_from_route}" ]]; then
      echo "$ip_from_route"
      return
    fi
  fi

  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i !~ /^127\./) {print $i; exit}}'
    return
  fi

  echo ""
}

if [[ -z "$LAN_HOST" ]]; then
  LAN_HOST="$(detect_lan_ip | tr -d '[:space:]')"
fi

if [[ -z "$LAN_HOST" ]]; then
  echo "[ERROR] Failed to determine LAN host. Set LAN_HOST manually."
  exit 1
fi

WEB_BASE="${LAN_PROTOCOL}://${LAN_HOST}:${LAN_PORT}"
printf '%s\n' "$WEB_BASE" > "$URL_FILE"
: > "$LEGACY_URL_FILE"

echo "[OK] Wrote self-register base: $WEB_BASE"
echo "[OK] File: $URL_FILE"
echo "[TIP] Patients must be on the same Wi-Fi/LAN to access this address."