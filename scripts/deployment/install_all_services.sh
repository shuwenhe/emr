#!/usr/bin/env bash
# Install all EMR systemd user services (backend, frontend, auto-git-push).
# Run once after clone or whenever services need to be reset.
#   bash scripts/deployment/install_all_services.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

install_service() {
  local name="$1"
  local template="${SCRIPT_DIR}/${name}.service.template"
  local dest="${SYSTEMD_USER_DIR}/${name}.service"

  if [[ ! -f "${template}" ]]; then
    echo "[skip] template not found: ${template}"
    return
  fi

  mkdir -p "${SYSTEMD_USER_DIR}"
  sed \
    -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
    "${template}" > "${dest}"

  echo "[ok] installed ${dest}"
}

mkdir -p "${PROJECT_ROOT}/logs"

# Install service files
install_service emr-backend
install_service emr-frontend
install_service emr-auto-git-push
install_service emr-auto-deploy

systemctl --user daemon-reload

# Enable and start all services
for svc in emr-backend emr-frontend emr-auto-git-push emr-auto-deploy; do
  if [[ -f "${SYSTEMD_USER_DIR}/${svc}.service" ]]; then
    systemctl --user enable --now "${svc}" 2>/dev/null || systemctl --user restart "${svc}" || true
    echo "[ok] ${svc}: $(systemctl --user is-active ${svc} 2>/dev/null || echo unknown)"
  fi
done

# Enable linger so services survive reboot even before login
LINGER_STATUS="$(loginctl show-user "${USER}" -p Linger 2>/dev/null | cut -d= -f2 || true)"
if [[ "${LINGER_STATUS}" != "yes" ]]; then
  if sudo -n loginctl enable-linger "${USER}" >/dev/null 2>&1; then
    echo "[ok] linger enabled (services survive reboot)"
  else
    echo "[warn] linger not enabled — run: sudo loginctl enable-linger ${USER}"
  fi
else
  echo "[ok] linger already enabled"
fi

echo ""
echo "All services installed. Useful commands:"
echo "  systemctl --user status emr-backend emr-frontend emr-auto-git-push emr-auto-deploy"
echo "  journalctl --user -u emr-frontend -f"
echo "  journalctl --user -u emr-backend -f"
echo "  journalctl --user -u emr-auto-deploy -f"
