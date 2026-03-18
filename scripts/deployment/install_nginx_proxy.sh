#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/emr-nginx.conf.template"

NGINX_CONF_NAME="${NGINX_CONF_NAME:-emr.conf}"
SERVER_NAME="${SERVER_NAME:-_}"
BACKEND_UPSTREAM="${BACKEND_UPSTREAM:-127.0.0.1:8000}"
FRONTEND_UPSTREAM="${FRONTEND_UPSTREAM:-127.0.0.1:3000}"
TARGET_FILE="/etc/nginx/conf.d/${NGINX_CONF_NAME}"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "[error] missing template: ${TEMPLATE_FILE}" >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "[error] nginx not found. install first: sudo apt install -y nginx" >&2
  exit 1
fi

TMP_CONF="$(mktemp)"
trap 'rm -f "${TMP_CONF}"' EXIT

sed \
  -e "s|__SERVER_NAME__|${SERVER_NAME}|g" \
  -e "s|__BACKEND_UPSTREAM__|${BACKEND_UPSTREAM}|g" \
  -e "s|__FRONTEND_UPSTREAM__|${FRONTEND_UPSTREAM}|g" \
  "${TEMPLATE_FILE}" > "${TMP_CONF}"

sudo cp "${TMP_CONF}" "${TARGET_FILE}"
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx

echo "[ok] installed nginx conf: ${TARGET_FILE}"
echo "[ok] backend upstream: ${BACKEND_UPSTREAM}"
echo "[ok] frontend upstream: ${FRONTEND_UPSTREAM}"

echo
echo "Health check URLs:"
echo "  curl -i http://127.0.0.1/nginx-healthz"
echo "  curl -i http://127.0.0.1/healthz"
echo "  curl -i http://127.0.0.1/readyz"

echo
echo "Useful commands:"
echo "  sudo nginx -t"
echo "  sudo systemctl reload nginx"
echo "  sudo journalctl -u nginx -f"
