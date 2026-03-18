#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"

docker compose \
  -f docker/docker-compose.prod.yml \
  -f docker/docker-compose.public-domain.yml \
  --env-file docker/.env.public \
  down

echo "[DONE] Public domain stack stopped."
