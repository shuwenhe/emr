#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/emr-ingestion.service.template"

SERVICE_NAME="${SERVICE_NAME:-emr-ingestion}"
APP_USER="${APP_USER:-$(id -un)}"
APP_GROUP="${APP_GROUP:-$(id -gn)}"
APP_MODULE="${APP_MODULE:-route.main:app}"
APP_PORT="${APP_PORT:-8000}"
VENV_PY="${VENV_PY:-${PROJECT_ROOT}/.venv/bin/python}"
SYSTEMD_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "[error] missing template: ${TEMPLATE_FILE}" >&2
  exit 1
fi

if [[ ! -x "${VENV_PY}" ]]; then
  cat >&2 <<EOF
[error] Python executable not found: ${VENV_PY}
Hint:
  1) cd ${PROJECT_ROOT}
  2) make install
EOF
  exit 1
fi

mkdir -p "${PROJECT_ROOT}/logs"

TMP_SERVICE="$(mktemp)"
trap 'rm -f "${TMP_SERVICE}"' EXIT

sed \
  -e "s|__SERVICE_NAME__|${SERVICE_NAME}|g" \
  -e "s|__APP_USER__|${APP_USER}|g" \
  -e "s|__APP_GROUP__|${APP_GROUP}|g" \
  -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
  -e "s|__APP_MODULE__|${APP_MODULE}|g" \
  -e "s|__APP_PORT__|${APP_PORT}|g" \
  -e "s|__VENV_PY__|${VENV_PY}|g" \
  "${TEMPLATE_FILE}" > "${TMP_SERVICE}"

sudo cp "${TMP_SERVICE}" "${SYSTEMD_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[ok] installed: ${SYSTEMD_FILE}"
echo "[ok] active status:"
sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,20p'

echo
echo "Useful commands:"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
