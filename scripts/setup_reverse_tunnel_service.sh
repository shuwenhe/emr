#!/usr/bin/env bash
set -euo pipefail

# One-click setup for a persistent reverse SSH tunnel service on the internal host.
# It creates a systemd unit with auto-restart so tunnel reconnects after disconnects.
#
# Default behavior:
# - Public gateway: root@111.202.231.146:4430
# - Remote bind: 127.0.0.1:13000 (on public host)
# - Local target: 127.0.0.1:80 (on internal host)
#
# Usage:
#   sudo bash scripts/setup_reverse_tunnel_service.sh
#   sudo bash scripts/setup_reverse_tunnel_service.sh --install-key
#   sudo bash scripts/setup_reverse_tunnel_service.sh \
#     --public-host 111.202.231.146 --public-port 4430 --public-user root \
#     --remote-port 13000 --local-port 80

PUBLIC_HOST="111.202.231.146"
PUBLIC_PORT="4430"
PUBLIC_USER="root"

REMOTE_BIND_ADDR="127.0.0.1"
REMOTE_BIND_PORT="13000"
LOCAL_TARGET_ADDR="127.0.0.1"
LOCAL_TARGET_PORT="80"

SERVICE_NAME="emr-reverse-tunnel"
SSH_BIN="$(command -v ssh || true)"
SSH_COPY_ID_BIN="$(command -v ssh-copy-id || true)"
SSH_KEYGEN_BIN="$(command -v ssh-keygen || true)"
IDENTITY_FILE="/root/.ssh/id_ed25519"
INSTALL_KEY="false"

log() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
err() { echo "[ERROR] $*"; }

usage() {
  sed -n '1,120p' "$0"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Please run as root: sudo bash $0"
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --public-host)
        PUBLIC_HOST="$2"; shift 2 ;;
      --public-port)
        PUBLIC_PORT="$2"; shift 2 ;;
      --public-user)
        PUBLIC_USER="$2"; shift 2 ;;
      --remote-bind-addr)
        REMOTE_BIND_ADDR="$2"; shift 2 ;;
      --remote-port)
        REMOTE_BIND_PORT="$2"; shift 2 ;;
      --local-addr)
        LOCAL_TARGET_ADDR="$2"; shift 2 ;;
      --local-port)
        LOCAL_TARGET_PORT="$2"; shift 2 ;;
      --service-name)
        SERVICE_NAME="$2"; shift 2 ;;
      --identity-file)
        IDENTITY_FILE="$2"; shift 2 ;;
      --install-key)
        INSTALL_KEY="true"; shift ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        err "Unknown argument: $1"
        exit 1 ;;
    esac
  done
}

ensure_prereqs() {
  if [[ -z "$SSH_BIN" ]]; then
    err "ssh command not found. Install openssh-client first."
    exit 1
  fi

  if ! command -v systemctl >/dev/null 2>&1; then
    err "systemctl not found. This script requires systemd."
    exit 1
  fi
}

ensure_ssh_key() {
  local key_dir
  key_dir="$(dirname "$IDENTITY_FILE")"
  mkdir -p "$key_dir"
  chmod 700 "$key_dir"

  if [[ ! -f "$IDENTITY_FILE" ]]; then
    if [[ -z "$SSH_KEYGEN_BIN" ]]; then
      err "ssh-keygen command not found, cannot create identity key."
      exit 1
    fi
    log "Generating SSH key at ${IDENTITY_FILE}"
    "$SSH_KEYGEN_BIN" -t ed25519 -N "" -f "$IDENTITY_FILE"
  fi

  chmod 600 "$IDENTITY_FILE"
}

install_public_key_if_requested() {
  if [[ "$INSTALL_KEY" != "true" ]]; then
    return 0
  fi

  if [[ -z "$SSH_COPY_ID_BIN" ]]; then
    err "ssh-copy-id not found. Install openssh-client package first."
    exit 1
  fi

  ensure_ssh_key

  log "Installing public key to ${PUBLIC_USER}@${PUBLIC_HOST}:${PUBLIC_PORT}"
  log "A password prompt may appear once to complete key installation."
  "$SSH_COPY_ID_BIN" -p "$PUBLIC_PORT" -i "${IDENTITY_FILE}.pub" "${PUBLIC_USER}@${PUBLIC_HOST}"
}

check_non_interactive_ssh() {
  set +e
  "$SSH_BIN" -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new \
    -p "$PUBLIC_PORT" -i "$IDENTITY_FILE" "${PUBLIC_USER}@${PUBLIC_HOST}" true >/dev/null 2>&1
  local rc=$?
  set -e

  if [[ $rc -ne 0 ]]; then
    warn "Non-interactive SSH login is not ready yet."
    warn "Run this script with --install-key, or manually install ${IDENTITY_FILE}.pub on public host."
  else
    log "Non-interactive SSH login check: OK"
  fi
}

write_service() {
  local service_path
  service_path="/etc/systemd/system/${SERVICE_NAME}.service"

  log "Writing systemd unit: ${service_path}"
  cat >"$service_path" <<EOF
[Unit]
Description=EMR Reverse SSH Tunnel to Public Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=${SSH_BIN} -NT \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o TCPKeepAlive=yes \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=10 \
  -i ${IDENTITY_FILE} \
  -p ${PUBLIC_PORT} \
  -R ${REMOTE_BIND_ADDR}:${REMOTE_BIND_PORT}:${LOCAL_TARGET_ADDR}:${LOCAL_TARGET_PORT} \
  ${PUBLIC_USER}@${PUBLIC_HOST}
Restart=always
RestartSec=5
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
EOF
}

enable_and_start_service() {
  log "Reloading systemd"
  systemctl daemon-reload

  log "Enabling service: ${SERVICE_NAME}"
  systemctl enable "$SERVICE_NAME" >/dev/null

  log "Restarting service: ${SERVICE_NAME}"
  systemctl restart "$SERVICE_NAME"

  log "Service status"
  systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,40p'
}

print_validation_guide() {
  cat <<EOF

[NEXT CHECKS]
1) On the public gateway host, verify tunnel port is listening:
   ss -lntp | grep :${REMOTE_BIND_PORT}

2) On the public gateway host, verify upstream responds:
   curl -I http://127.0.0.1:${REMOTE_BIND_PORT}/emr/

3) On the public gateway host, run gateway deploy script if needed:
   sudo bash /app/emr/scripts/deploy_public_gateway.sh --tunnel-port ${REMOTE_BIND_PORT}

EOF
}

main() {
  require_root
  parse_args "$@"
  ensure_prereqs
  ensure_ssh_key
  install_public_key_if_requested
  check_non_interactive_ssh
  write_service
  enable_and_start_service
  print_validation_guide
}

main "$@"
