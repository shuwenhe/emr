#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

FUNNEL_PORT="${FUNNEL_PORT:-3000}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "[ERROR] tailscale command not found. Install Tailscale first."
  exit 1
fi

dns_name_raw="$(tailscale status --json 2>/dev/null | grep -m1 '"DNSName"' | sed -E 's/.*"DNSName":\s*"([^"]+)".*/\1/' || true)"
dns_name="${dns_name_raw%.}"

if [[ -z "$dns_name" ]]; then
  echo "[ERROR] Failed to detect node DNS name from tailscale status."
  exit 1
fi

set +e
funnel_output="$(timeout 10 tailscale funnel --bg "$FUNNEL_PORT" 2>&1)"
funnel_code=$?
set -e

if [[ $funnel_code -ne 0 ]]; then
  echo "$funnel_output"
  echo "[ERROR] Failed to enable Tailscale Funnel."
  if [[ $funnel_code -eq 124 ]]; then
    echo "[TIP] tailscale funnel command timed out (likely waiting on admin approval)."
  fi
  echo "[TIP] Open the Tailscale admin link above, enable Funnel for this node, then rerun this script."
  exit 1
fi

WEB_BASE="https://${dns_name}"
printf '%s\n' "$WEB_BASE" > "$URL_FILE"
: > "$LEGACY_URL_FILE"

echo "[OK] Tailscale Funnel is enabled for local port ${FUNNEL_PORT}."
echo "[OK] Wrote public self-register base: $WEB_BASE"
echo "[OK] File: $URL_FILE"
echo "[TIP] Open /patients -> 微信扫码登记 to use the updated QR code."