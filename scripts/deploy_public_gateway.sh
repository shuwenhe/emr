#!/usr/bin/env bash
set -euo pipefail

# One-click gateway setup for EMR on a public host.
# - Auto-detects upstream: direct internal host or local reverse-tunnel port
# - Writes nginx site config
# - Tests and reloads nginx
# - Runs basic health checks
#
# Usage examples:
#   sudo bash scripts/deploy_public_gateway.sh
#   sudo bash scripts/deploy_public_gateway.sh --internal-host 192.168.132.60 --domain emr.example.com --https
#   sudo bash scripts/deploy_public_gateway.sh --tunnel-port 13000

INTERNAL_HOST="192.168.132.60"
INTERNAL_PORT="80"
TUNNEL_HOST="127.0.0.1"
TUNNEL_PORT="13000"
DOMAIN=""
ENABLE_HTTPS="false"
SITE_FILE="/etc/nginx/sites-enabled/default"
NGINX_BIN="$(command -v nginx || true)"

ok_codes='200|201|204|301|302|307|308|401|403'

log() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
err() { echo "[ERROR] $*"; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Please run as root: sudo bash $0"
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --internal-host)
        INTERNAL_HOST="$2"; shift 2 ;;
      --internal-port)
        INTERNAL_PORT="$2"; shift 2 ;;
      --tunnel-port)
        TUNNEL_PORT="$2"; shift 2 ;;
      --domain)
        DOMAIN="$2"; shift 2 ;;
      --https)
        ENABLE_HTTPS="true"; shift ;;
      -h|--help)
        sed -n '1,80p' "$0"
        exit 0 ;;
      *)
        err "Unknown argument: $1"
        exit 1 ;;
    esac
  done
}

check_http() {
  local url="$1"
  local code
  code="$(curl -m 4 -s -o /dev/null -w '%{http_code}' "$url" || true)"
  if echo "$code" | grep -Eq "^(${ok_codes})$"; then
    echo "$code"
    return 0
  fi
  return 1
}

choose_upstream() {
  local direct_base="http://${INTERNAL_HOST}:${INTERNAL_PORT}"
  local tunnel_base="http://${TUNNEL_HOST}:${TUNNEL_PORT}"

  log "Probing direct upstream: ${direct_base}/emr"
  if code="$(check_http "${direct_base}/emr")"; then
    log "Direct upstream reachable (HTTP ${code})"
    echo "$direct_base"
    return 0
  fi

  log "Probing tunnel upstream: ${tunnel_base}/emr"
  if code="$(check_http "${tunnel_base}/emr")"; then
    log "Tunnel upstream reachable (HTTP ${code})"
    echo "$tunnel_base"
    return 0
  fi

  err "Neither direct (${direct_base}) nor tunnel (${tunnel_base}) upstream is reachable."
  err "If using reverse tunnel, start it on internal host:"
  err "ssh -p 4430 -N -R 127.0.0.1:${TUNNEL_PORT}:127.0.0.1:80 root@<public-host>"
  exit 1
}

write_nginx_conf() {
  local upstream="$1"
  local server_name="_"

  if [[ -n "$DOMAIN" ]]; then
    server_name="$DOMAIN"
  fi

  log "Writing nginx config to ${SITE_FILE}"
  cat >"${SITE_FILE}" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${server_name};

    client_max_body_size 50m;

    location = / {
        return 302 /emr/;
    }

    location = /emr {
        proxy_pass ${upstream}/emr;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /emr/ {
        proxy_pass ${upstream}/emr/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /emr/api/ {
        proxy_pass ${upstream}/emr/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
}

reload_nginx() {
  if [[ -z "$NGINX_BIN" ]]; then
    err "nginx is not installed on this machine."
    exit 1
  fi

  log "Testing nginx config"
  nginx -t

  log "Reloading nginx"
  systemctl enable nginx >/dev/null 2>&1 || true
  systemctl reload nginx
}

setup_https_if_requested() {
  if [[ "$ENABLE_HTTPS" != "true" ]]; then
    return 0
  fi

  if [[ -z "$DOMAIN" ]]; then
    warn "--https requested but --domain not provided. Skipping HTTPS."
    return 0
  fi

  log "Installing certbot (if missing)"
  apt-get update -y
  apt-get install -y certbot python3-certbot-nginx

  log "Issuing HTTPS certificate for ${DOMAIN}"
  certbot --nginx -d "${DOMAIN}" --redirect --agree-tos -m "admin@${DOMAIN}" -n
}

print_health_checks() {
  local host_target
  host_target="127.0.0.1"

  log "Health checks"
  echo "-----"
  curl -sI "http://${host_target}/emr/" | sed -n '1,10p'
  echo "-----"

  if [[ -n "$DOMAIN" ]]; then
    curl -sI "http://${DOMAIN}/emr/" | sed -n '1,10p' || true
    echo "-----"
    if [[ "$ENABLE_HTTPS" == "true" ]]; then
      curl -sI "https://${DOMAIN}/emr/" | sed -n '1,10p' || true
      echo "-----"
    fi
  fi

  local pub_ip
  pub_ip="$(hostname -I | awk '{print $1}')"
  if [[ -n "$pub_ip" ]]; then
    curl -sI "http://${pub_ip}/emr/" | sed -n '1,10p' || true
  fi
}

main() {
  require_root
  parse_args "$@"

  local upstream
  upstream="$(choose_upstream)"
  write_nginx_conf "$upstream"
  reload_nginx
  setup_https_if_requested
  print_health_checks

  log "Done. If external browser still sees 'Welcome to nginx', you are hitting a different public host."
}

main "$@"
