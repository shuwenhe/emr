#!/usr/bin/env bash
set -euo pipefail

# Orchestrator for EMR public access rollout from the internal host.
# It chains:
# 1) setup_reverse_tunnel_service.sh (internal host)
# 2) prints exactly one public-host command for deploy_public_gateway.sh
# 3) outputs a full validation report (PASS/FAIL)
#
# Usage:
#   sudo bash scripts/orchestrate_public_access.sh --install-key
#   sudo bash scripts/orchestrate_public_access.sh --domain emr.example.com --https --install-key

PUBLIC_HOST="111.202.231.146"
PUBLIC_PORT="4430"
PUBLIC_USER="root"
REMOTE_PORT="13000"
LOCAL_PORT="80"
LOCAL_ADDR="127.0.0.1"
SERVICE_NAME="emr-reverse-tunnel"
DOMAIN=""
ENABLE_HTTPS="false"
INSTALL_KEY="false"
PUBLIC_SCRIPT_PATH="/app/emr/scripts/deploy_public_gateway.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_TUNNEL_SCRIPT="${SCRIPT_DIR}/setup_reverse_tunnel_service.sh"

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass() { echo "[PASS] $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "[FAIL] $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
warn() { echo "[WARN] $*"; WARN_COUNT=$((WARN_COUNT + 1)); }
info() { echo "[INFO] $*"; }

usage() {
  cat <<EOF
Usage:
  sudo bash scripts/orchestrate_public_access.sh [options]

Options:
  --public-host <host>        Public gateway host (default: ${PUBLIC_HOST})
  --public-port <port>        Public gateway ssh port (default: ${PUBLIC_PORT})
  --public-user <user>        Public gateway ssh user (default: ${PUBLIC_USER})
  --remote-port <port>        Remote bind port on public host (default: ${REMOTE_PORT})
  --local-port <port>         Local target port on internal host (default: ${LOCAL_PORT})
  --local-addr <addr>         Local target addr on internal host (default: ${LOCAL_ADDR})
  --service-name <name>       systemd unit name for tunnel (default: ${SERVICE_NAME})
  --domain <fqdn>             Public domain for gateway script
  --https                     Include --https in public-side deploy command
  --install-key               Install ssh public key to public host during setup
  --public-script-path <path> Path of deploy_public_gateway.sh on public host
  -h, --help                  Show help
EOF
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "[ERROR] Please run as root: sudo bash $0"
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --public-host) PUBLIC_HOST="$2"; shift 2 ;;
      --public-port) PUBLIC_PORT="$2"; shift 2 ;;
      --public-user) PUBLIC_USER="$2"; shift 2 ;;
      --remote-port) REMOTE_PORT="$2"; shift 2 ;;
      --local-port) LOCAL_PORT="$2"; shift 2 ;;
      --local-addr) LOCAL_ADDR="$2"; shift 2 ;;
      --service-name) SERVICE_NAME="$2"; shift 2 ;;
      --domain) DOMAIN="$2"; shift 2 ;;
      --https) ENABLE_HTTPS="true"; shift ;;
      --install-key) INSTALL_KEY="true"; shift ;;
      --public-script-path) PUBLIC_SCRIPT_PATH="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *)
        echo "[ERROR] Unknown argument: $1"
        exit 1
        ;;
    esac
  done
}

check_file_exists() {
  local f="$1"
  if [[ -f "$f" ]]; then
    pass "Found required script: $f"
  else
    fail "Missing required script: $f"
  fi
}

run_tunnel_setup() {
  local args=()
  args+=(--public-host "$PUBLIC_HOST")
  args+=(--public-port "$PUBLIC_PORT")
  args+=(--public-user "$PUBLIC_USER")
  args+=(--remote-port "$REMOTE_PORT")
  args+=(--local-addr "$LOCAL_ADDR")
  args+=(--local-port "$LOCAL_PORT")
  args+=(--service-name "$SERVICE_NAME")
  if [[ "$INSTALL_KEY" == "true" ]]; then
    args+=(--install-key)
  fi

  info "Running tunnel setup script"
  if bash "$SETUP_TUNNEL_SCRIPT" "${args[@]}"; then
    pass "Tunnel setup script completed"
  else
    fail "Tunnel setup script failed"
  fi
}

check_systemd_active() {
  local svc="$1"
  local state
  state="$(systemctl is-active "$svc" 2>/dev/null || true)"
  if [[ "$state" == "active" ]]; then
    pass "Service active: ${svc}"
  else
    fail "Service not active: ${svc} (state=${state:-unknown})"
  fi
}

check_http_ok() {
  local url="$1"
  local code
  code="$(curl -m 5 -s -o /dev/null -w '%{http_code}' "$url" || true)"
  if echo "$code" | grep -Eq '^(200|201|204|301|302|307|308|401|403)$'; then
    pass "HTTP reachable: ${url} (code=${code})"
  else
    fail "HTTP unreachable: ${url} (code=${code:-n/a})"
  fi
}

check_ssh_batch() {
  if ssh -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new \
    -p "$PUBLIC_PORT" "${PUBLIC_USER}@${PUBLIC_HOST}" true >/dev/null 2>&1; then
    pass "Non-interactive SSH to public host is ready"
    return 0
  fi

  warn "Non-interactive SSH to public host is not ready"
  return 1
}

check_remote_tunnel_port() {
  local listen_out curl_out

  set +e
  listen_out="$(ssh -o BatchMode=yes -o ConnectTimeout=6 -p "$PUBLIC_PORT" "${PUBLIC_USER}@${PUBLIC_HOST}" \
    "ss -lnt | grep -E ':${REMOTE_PORT}\\b'" 2>/dev/null)"
  local rc1=$?
  curl_out="$(ssh -o BatchMode=yes -o ConnectTimeout=6 -p "$PUBLIC_PORT" "${PUBLIC_USER}@${PUBLIC_HOST}" \
    "curl -m 5 -s -o /dev/null -w '%{http_code}' http://127.0.0.1:${REMOTE_PORT}/emr/" 2>/dev/null)"
  local rc2=$?
  set -e

  if [[ $rc1 -eq 0 && -n "$listen_out" ]]; then
    pass "Remote tunnel port is listening on public host (${REMOTE_PORT})"
  else
    fail "Remote tunnel port is not listening on public host (${REMOTE_PORT})"
  fi

  if [[ $rc2 -eq 0 ]] && echo "$curl_out" | grep -Eq '^(200|201|204|301|302|307|308|401|403)$'; then
    pass "Remote tunnel upstream check passed on public host (code=${curl_out})"
  else
    fail "Remote tunnel upstream check failed on public host (code=${curl_out:-n/a})"
  fi
}

build_public_command() {
  local cmd
  cmd="ssh -p ${PUBLIC_PORT} ${PUBLIC_USER}@${PUBLIC_HOST} \"sudo bash ${PUBLIC_SCRIPT_PATH} --tunnel-port ${REMOTE_PORT}"
  if [[ -n "$DOMAIN" ]]; then
    cmd+=" --domain ${DOMAIN}"
  fi
  if [[ "$ENABLE_HTTPS" == "true" ]]; then
    cmd+=" --https"
  fi
  cmd+="\""
  echo "$cmd"
}

print_report() {
  local public_cmd
  public_cmd="$(build_public_command)"

  echo
  echo "================ EMR Public Access Report ================"
  echo "Internal host: $(hostname -f 2>/dev/null || hostname)"
  echo "Public host  : ${PUBLIC_USER}@${PUBLIC_HOST}:${PUBLIC_PORT}"
  echo "Tunnel map   : ${PUBLIC_HOST}:${REMOTE_PORT} -> ${LOCAL_ADDR}:${LOCAL_PORT}"
  echo "Service name : ${SERVICE_NAME}"
  echo "----------------------------------------------------------"
  echo "PASS=${PASS_COUNT} WARN=${WARN_COUNT} FAIL=${FAIL_COUNT}"
  echo "----------------------------------------------------------"
  echo "Run this single command on internal host to configure public gateway:"
  echo "$public_cmd"
  echo "----------------------------------------------------------"
  echo "Final browser URL:"
  if [[ -n "$DOMAIN" ]]; then
    if [[ "$ENABLE_HTTPS" == "true" ]]; then
      echo "https://${DOMAIN}/emr/"
    else
      echo "http://${DOMAIN}/emr/"
    fi
  else
    echo "http://${PUBLIC_HOST}/emr/"
  fi
  echo "=========================================================="
}

main() {
  require_root
  parse_args "$@"

  check_file_exists "$SETUP_TUNNEL_SCRIPT"

  if [[ $FAIL_COUNT -gt 0 ]]; then
    print_report
    exit 1
  fi

  run_tunnel_setup
  check_systemd_active "$SERVICE_NAME"

  # Optional local checks (do not block rollout if services are named differently)
  check_systemd_active "emr-frontend"
  check_systemd_active "nginx"
  check_http_ok "http://127.0.0.1/emr/"

  if check_ssh_batch; then
    check_remote_tunnel_port
  else
    warn "Skip remote tunnel validation because SSH batch login is unavailable"
  fi

  print_report

  if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
