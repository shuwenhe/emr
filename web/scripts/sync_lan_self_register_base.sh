#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

LAN_PORT="${LAN_PORT:-3000}"
LAN_PROTOCOL="${LAN_PROTOCOL:-http}"
LAN_HOST="${LAN_HOST:-}"

detect_lan_ip() {
  # Prefer real LAN IPs (192.168.x.x or 10.x.x.x) from physical/wireless interfaces.
  # Skips loopback, Docker bridges, VPN/tunnel interfaces (tailscale, FlClash, tun, etc.).
  if command -v ip >/dev/null 2>&1; then
    local lan_ip
    lan_ip="$(ip addr show \
      | awk '
          /^[0-9]+: / { iface=$2; gsub(/:$/, "", iface) }
          /inet / {
            split($2, a, "/"); ip=a[1]
            # Skip loopback, docker, bridge, VPN-like interfaces
            if (iface ~ /^(lo|docker|br-|veth|tun|tap|virbr|FlClash|tailscale|wg|utun)/) next
            # Prefer private LAN ranges: 192.168.x.x or 10.x.x.x
            if (ip ~ /^192\.168\./ || ip ~ /^10\./) { print ip; exit }
          }
        ')"
    if [[ -n "${lan_ip}" ]]; then
      echo "${lan_ip}"
      return
    fi

    # Fallback: any non-loopback, non-VPN IP
    lan_ip="$(ip addr show \
      | awk '
          /^[0-9]+: / { iface=$2; gsub(/:$/, "", iface) }
          /inet / {
            split($2, a, "/"); ip=a[1]
            if (iface ~ /^(lo|docker|br-|veth|tun|tap|virbr|FlClash|tailscale|wg|utun)/) next
            if (ip !~ /^127\./) { print ip; exit }
          }
        ')"
    if [[ -n "${lan_ip}" ]]; then
      echo "${lan_ip}"
      return
    fi
  fi

  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i ~ /^192\.168\./ || $i ~ /^10\./) {print $i; exit}}'
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