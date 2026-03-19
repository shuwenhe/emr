#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
START_SCRIPT="${PROJECT_ROOT}/scripts/start_auto_git_push.sh"
LOG_FILE="${PROJECT_ROOT}/.git/.auto-git-push.log"
CRON_CMD="cd ${PROJECT_ROOT} && bash ${START_SCRIPT} >> ${LOG_FILE} 2>&1"
CRON_LINE="@reboot ${CRON_CMD}"

if [[ ! -x "${START_SCRIPT}" ]]; then
  echo "[error] start script not found or not executable: ${START_SCRIPT}" >&2
  exit 1
fi

CURRENT_CRON="$(crontab -l 2>/dev/null || true)"
if printf '%s\n' "${CURRENT_CRON}" | grep -Fqx "${CRON_LINE}"; then
  echo "[ok] cron @reboot entry already exists"
  exit 0
fi

TMP_CRON="$(mktemp)"
trap 'rm -f "${TMP_CRON}"' EXIT

printf '%s\n' "${CURRENT_CRON}" > "${TMP_CRON}"
if [[ -n "${CURRENT_CRON}" ]]; then
  printf '\n' >> "${TMP_CRON}"
fi
printf '%s\n' "${CRON_LINE}" >> "${TMP_CRON}"

crontab "${TMP_CRON}"

echo "[ok] installed cron @reboot entry"
echo "[ok] entry: ${CRON_LINE}"
