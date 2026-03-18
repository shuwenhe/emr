#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

PUBLIC_WEB_BASE_URL="${PUBLIC_WEB_BASE_URL:-}"
PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-}"

if [[ -z "$PUBLIC_WEB_BASE_URL" ]]; then
  if [[ -n "$PUBLIC_DOMAIN" ]]; then
    PUBLIC_WEB_BASE_URL="https://${PUBLIC_DOMAIN}"
  fi
fi

PUBLIC_WEB_BASE_URL="$(printf '%s' "$PUBLIC_WEB_BASE_URL" | sed 's:/*$::')"

if [[ -z "$PUBLIC_WEB_BASE_URL" ]]; then
  echo "[ERROR] Missing PUBLIC_WEB_BASE_URL or PUBLIC_DOMAIN."
  echo "[TIP] Example: PUBLIC_DOMAIN=your-domain.com npm run share:public:sync"
  exit 1
fi

if [[ "$PUBLIC_WEB_BASE_URL" != http://* && "$PUBLIC_WEB_BASE_URL" != https://* ]]; then
  echo "[ERROR] PUBLIC_WEB_BASE_URL must start with http:// or https://"
  exit 1
fi

printf '%s\n' "$PUBLIC_WEB_BASE_URL" > "$URL_FILE"
: > "$LEGACY_URL_FILE"

echo "[OK] Wrote public self-register base: $PUBLIC_WEB_BASE_URL"
echo "[OK] File: $URL_FILE"
echo "[TIP] QR register URL will be: ${PUBLIC_WEB_BASE_URL}/self-register"