#!/usr/bin/env bash
set -euo pipefail

# One-click installer + launcher for MindIE.
# Supports:
# - .deb package install via dpkg
# - .run package install via bash installer
# - auto-discover mindie server binary
# - start server in background with pid/log files
#
# Usage examples:
#   bash ./scripts/install_and_start_mindie.sh \
#     --package /root/Ascend-mindie_xxx.deb \
#     --config /root/mindie_qwen1.7b_8card.yaml
#
#   bash ./scripts/install_and_start_mindie.sh \
#     --config /root/mindie_qwen1.7b_8card.yaml

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PACKAGE_PATH=""
CONFIG_PATH=""
START_ONLY="0"
LOG_PATH="${REPO_DIR}/.run/mindie-server.log"
PID_PATH="${REPO_DIR}/.run/mindie-server.pid"

print_usage() {
  cat <<'EOF'
Usage:
  install_and_start_mindie.sh --config <mindie_config.yaml> [options]

Options:
  --package <path>      MindIE installer package (.deb or .run)
  --config <path>       MindIE server config file (required)
  --start-only          Skip installation, only locate and start
  --log <path>          Log file path (default: /app/emr/.run/mindie-server.log)
  --pid <path>          PID file path (default: /app/emr/.run/mindie-server.pid)
  -h, --help            Show this help
EOF
}

abs_path() {
  local p="$1"
  if [[ -d "$p" ]]; then
    (cd "$p" && pwd)
  else
    local d
    d="$(cd "$(dirname "$p")" && pwd)"
    echo "${d}/$(basename "$p")"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package)
      PACKAGE_PATH="${2:-}"
      shift 2
      ;;
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    --start-only)
      START_ONLY="1"
      shift 1
      ;;
    --log)
      LOG_PATH="${2:-}"
      shift 2
      ;;
    --pid)
      PID_PATH="${2:-}"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      print_usage
      exit 1
      ;;
  esac
done

if [[ -z "$CONFIG_PATH" ]]; then
  echo "[ERROR] --config is required"
  print_usage
  exit 1
fi
CONFIG_PATH="$(abs_path "$CONFIG_PATH")"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[ERROR] Config file not found: $CONFIG_PATH"
  exit 1
fi

mkdir -p "$(dirname "$LOG_PATH")"
mkdir -p "$(dirname "$PID_PATH")"

install_mindie_package() {
  local pkg="$1"
  if [[ -z "$pkg" ]]; then
    return 0
  fi
  pkg="$(abs_path "$pkg")"

  if [[ ! -f "$pkg" ]]; then
    echo "[ERROR] Package file not found: $pkg"
    exit 1
  fi

  echo "[INFO] Installing package: $pkg"
  if [[ "$pkg" == *.deb ]]; then
    dpkg -i "$pkg"
  elif [[ "$pkg" == *.run ]]; then
    bash "$pkg" --install
  else
    echo "[ERROR] Unsupported package type: $pkg (expect .deb or .run)"
    exit 1
  fi
}

source_ascend_env() {
  local candidates=(
    "/usr/local/Ascend/ascend-toolkit/set_env.sh"
    "/usr/local/Ascend/ascend-toolkit/latest/set_env.sh"
  )

  for c in "${candidates[@]}"; do
    if [[ -f "$c" ]]; then
      # shellcheck disable=SC1090
      source "$c"
      echo "[INFO] Loaded Ascend env: $c"
      return 0
    fi
  done

  echo "[WARN] set_env.sh not found under /usr/local/Ascend/ascend-toolkit"
  echo "[WARN] Continue without sourcing Ascend env"
  return 0
}

find_mindie_server() {
  local from_path
  from_path="$(command -v mindie-server || true)"
  if [[ -n "$from_path" ]]; then
    echo "$from_path"
    return 0
  fi

  local search_roots=(
    "/usr/local/Ascend"
    "/opt"
    "/usr/local/bin"
    "/usr/bin"
  )

  local found=""
  for root in "${search_roots[@]}"; do
    if [[ ! -e "$root" ]]; then
      continue
    fi
    found="$(find "$root" -type f \( -name 'mindie-server' -o -name 'mindie_server' -o -name 'mindie-service' -o -name 'mindie' \) 2>/dev/null | head -n 1 || true)"
    if [[ -n "$found" ]]; then
      echo "$found"
      return 0
    fi
  done

  return 1
}

stop_old_process_if_any() {
  if [[ -f "$PID_PATH" ]]; then
    local old_pid
    old_pid="$(cat "$PID_PATH" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
      echo "[INFO] Stopping old mindie process pid=$old_pid"
      kill "$old_pid" || true
      sleep 1
    fi
    rm -f "$PID_PATH"
  fi
}

start_mindie_server() {
  local bin_path="$1"
  local cfg_path="$2"

  stop_old_process_if_any

  echo "[INFO] Starting MindIE"
  echo "[INFO] Binary: $bin_path"
  echo "[INFO] Config: $cfg_path"
  echo "[INFO] Log:    $LOG_PATH"

  nohup "$bin_path" --config "$cfg_path" >> "$LOG_PATH" 2>&1 &
  local new_pid=$!
  echo "$new_pid" > "$PID_PATH"

  sleep 2
  if kill -0 "$new_pid" >/dev/null 2>&1; then
    echo "[OK] MindIE started, pid=$new_pid"
  else
    echo "[ERROR] MindIE failed to start, check log: $LOG_PATH"
    exit 1
  fi
}

main() {
  if [[ "$START_ONLY" != "1" ]]; then
    if [[ -n "$PACKAGE_PATH" ]]; then
      install_mindie_package "$PACKAGE_PATH"
    else
      echo "[INFO] No package provided, skip install and try start directly"
    fi
  fi

  source_ascend_env

  local mindie_bin
  mindie_bin="$(find_mindie_server || true)"
  if [[ -z "$mindie_bin" ]]; then
    echo "[ERROR] mindie-server binary not found"
    echo "[HINT] Install MindIE package first, then re-run with --package"
    exit 1
  fi

  start_mindie_server "$mindie_bin" "$CONFIG_PATH"

  echo "[INFO] Done"
  echo "[INFO] PID file: $PID_PATH"
  echo "[INFO] Log file: $LOG_PATH"
}

main "$@"
