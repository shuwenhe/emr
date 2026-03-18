#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WEB_DIR="${PROJECT_ROOT}/web"
TEMPLATE_FILE="${SCRIPT_DIR}/emr-cf-tunnel.service.template"

SERVICE_NAME="${SERVICE_NAME:-emr-cf-tunnel}"
APP_USER="${APP_USER:-$(id -un)}"
SYSTEMD_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "[error] missing template: ${TEMPLATE_FILE}" >&2
  exit 1
fi

TMP_SERVICE="$(mktemp)"
trap 'rm -f "${TMP_SERVICE}"' EXIT

sed \
  -e "s|__APP_USER__|${APP_USER}|g" \
  -e "s|__WEB_DIR__|${WEB_DIR}|g" \
  "${TEMPLATE_FILE}" > "${TMP_SERVICE}"

sudo cp "${TMP_SERVICE}" "${SYSTEMD_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[ok] installed: ${SYSTEMD_FILE}"
echo "[ok] status:"
sudo systemctl --no-pager status "${SERVICE_NAME}" | sed -n '1,15p'

echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  cat ${WEB_DIR}/public/tunnel-url.txt"
