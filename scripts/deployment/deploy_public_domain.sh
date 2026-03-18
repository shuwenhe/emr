#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$REPO_DIR/docker/.env.public"
EXAMPLE_FILE="$REPO_DIR/docker/.env.public.example"

DOMAIN="${1:-${PUBLIC_DOMAIN:-}}"
if [[ -z "$DOMAIN" ]]; then
  echo "[ERROR] Missing domain."
  echo "[USAGE] bash ./scripts/deployment/deploy_public_domain.sh your-domain.com"
  exit 1
fi

if [[ ! -f "$EXAMPLE_FILE" ]]; then
  echo "[ERROR] Missing $EXAMPLE_FILE"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$EXAMPLE_FILE" "$ENV_FILE"
fi

# Rewrite key vars idempotently.
sed -i "s#^PUBLIC_DOMAIN=.*#PUBLIC_DOMAIN=${DOMAIN}#" "$ENV_FILE"
sed -i "s#^NEXT_PUBLIC_SELF_REGISTER_BASE_URL=.*#NEXT_PUBLIC_SELF_REGISTER_BASE_URL=https://${DOMAIN}#" "$ENV_FILE"
sed -i "s#^PUBLIC_WEB_BASE_URL=.*#PUBLIC_WEB_BASE_URL=https://${DOMAIN}#" "$ENV_FILE"

if ! grep -q '^NEXT_PUBLIC_API_URL=' "$ENV_FILE"; then
  echo 'NEXT_PUBLIC_API_URL=/api' >> "$ENV_FILE"
fi

if ! grep -q '^PUBLIC_DOMAIN=' "$ENV_FILE"; then
  echo "PUBLIC_DOMAIN=${DOMAIN}" >> "$ENV_FILE"
fi

if ! grep -q '^NEXT_PUBLIC_SELF_REGISTER_BASE_URL=' "$ENV_FILE"; then
  echo "NEXT_PUBLIC_SELF_REGISTER_BASE_URL=https://${DOMAIN}" >> "$ENV_FILE"
fi

if ! grep -q '^PUBLIC_WEB_BASE_URL=' "$ENV_FILE"; then
  echo "PUBLIC_WEB_BASE_URL=https://${DOMAIN}" >> "$ENV_FILE"
fi

echo "[INFO] Using domain: $DOMAIN"
echo "[INFO] Env file: $ENV_FILE"

echo "[STEP] Deploying production stack + Caddy HTTPS reverse proxy..."
cd "$REPO_DIR"
docker compose \
  -f docker/docker-compose.prod.yml \
  -f docker/docker-compose.public-domain.yml \
  --env-file docker/.env.public \
  up -d --build

echo "[STEP] Syncing QR/self-register base URL..."
cd "$REPO_DIR/web"
PUBLIC_DOMAIN="$DOMAIN" npm run share:public:sync

echo "[STEP] Quick health checks..."
cd "$REPO_DIR"
curl -s -o /dev/null -w "[CHECK] http://${DOMAIN}/emr -> %{http_code} (%{time_total}s)\n" "http://${DOMAIN}/emr" || true
curl -k -s -o /dev/null -w "[CHECK] https://${DOMAIN}/emr -> %{http_code} (%{time_total}s)\n" "https://${DOMAIN}/emr" || true

echo "[DONE] Public domain deployment complete."
echo "[TIP] If HTTPS is not ready yet, wait DNS propagation and retry in 1-3 minutes."
echo "[TIP] In Cloudflare DNS, enable Proxied (orange cloud) for nearest edge routing."
