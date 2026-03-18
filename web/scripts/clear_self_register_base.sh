#!/usr/bin/env bash
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$WEB_DIR/public/self-register-base.txt"
LEGACY_URL_FILE="$WEB_DIR/public/tunnel-url.txt"

: > "$URL_FILE"
: > "$LEGACY_URL_FILE"

echo "[OK] Cleared shared self-register base files."