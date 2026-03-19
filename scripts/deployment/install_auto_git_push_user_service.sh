#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/emr-auto-git-push.service.template"

SERVICE_NAME="${SERVICE_NAME:-emr-auto-git-push}"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SYSTEMD_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "[error] missing template: ${TEMPLATE_FILE}" >&2
  exit 1
fi

mkdir -p "${PROJECT_ROOT}/logs"
mkdir -p "${SYSTEMD_USER_DIR}"

TMP_SERVICE="$(mktemp)"
trap 'rm -f "${TMP_SERVICE}"' EXIT

sed \
  -e "s|__SERVICE_NAME__|${SERVICE_NAME}|g" \
  -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
  "${TEMPLATE_FILE}" > "${TMP_SERVICE}"

cp "${TMP_SERVICE}" "${SYSTEMD_FILE}"

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}"

LINGER_STATUS="$(loginctl show-user "${USER}" -p Linger 2>/dev/null | cut -d= -f2 || true)"
if [[ "${LINGER_STATUS}" != "yes" ]]; then
  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo loginctl enable-linger "${USER}"
    LINGER_STATUS="yes"
  fi
fi

echo "[ok] installed user service: ${SYSTEMD_FILE}"
echo "[ok] active status:"
systemctl --user --no-pager --full status "${SERVICE_NAME}" | sed -n '1,20p'
echo
if [[ "${LINGER_STATUS}" == "yes" ]]; then
  echo "[ok] linger enabled: service will also survive reboot before login"
else
  echo "[warn] linger is not enabled: service will auto-start after user login only"
  echo "       To enable full reboot persistence, run: sudo loginctl enable-linger ${USER}"
fi
echo
echo "Useful commands:"
echo "  systemctl --user restart ${SERVICE_NAME}"
echo "  systemctl --user stop ${SERVICE_NAME}"
echo "  systemctl --user status ${SERVICE_NAME}"
echo "  journalctl --user -u ${SERVICE_NAME} -f"
