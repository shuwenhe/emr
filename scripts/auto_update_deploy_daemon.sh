#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

REMOTE="${AUTO_DEPLOY_REMOTE:-origin}"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
BRANCH="${AUTO_DEPLOY_BRANCH:-$CURRENT_BRANCH}"
INTERVAL_SECONDS="${AUTO_DEPLOY_INTERVAL_SECONDS:-20}"

# Default command deploys backend+web in production compose mode.
DEFAULT_DEPLOY_COMMAND='docker compose -f docker/docker-compose.prod.yml up -d --build web backend'
DEPLOY_COMMAND="${AUTO_DEPLOY_COMMAND:-$DEFAULT_DEPLOY_COMMAND}"
PRE_DEPLOY_COMMAND="${AUTO_DEPLOY_PRE_COMMAND:-}"
POST_DEPLOY_HEALTHCHECK_URL="${AUTO_DEPLOY_HEALTHCHECK_URL:-}"

log() {
  printf '[%s] [auto-deploy] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "watching ${REMOTE}/${BRANCH} every ${INTERVAL_SECONDS}s"
log "deploy command: ${DEPLOY_COMMAND}"

while true; do
  # Protect local modifications from being overwritten.
  if [[ -n "$(git status --porcelain)" ]]; then
    log "local changes detected, skip this cycle"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if ! git fetch --quiet "$REMOTE" "$BRANCH"; then
    log "git fetch failed for ${REMOTE}/${BRANCH}, retry later"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if ! git rev-parse --verify "${REMOTE}/${BRANCH}" >/dev/null 2>&1; then
    log "remote ref not found: ${REMOTE}/${BRANCH}"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  local_sha="$(git rev-parse HEAD)"
  remote_sha="$(git rev-parse "${REMOTE}/${BRANCH}")"

  if [[ "$local_sha" == "$remote_sha" ]]; then
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  log "new commit detected: ${local_sha:0:7} -> ${remote_sha:0:7}"

  if ! git pull --ff-only "$REMOTE" "$BRANCH"; then
    log "git pull --ff-only failed, manual intervention may be needed"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if [[ -n "$PRE_DEPLOY_COMMAND" ]]; then
    log "running pre-deploy command"
    if ! bash -lc "$PRE_DEPLOY_COMMAND"; then
      log "pre-deploy command failed"
      sleep "$INTERVAL_SECONDS"
      continue
    fi
  fi

  log "running deploy command"
  if ! bash -lc "$DEPLOY_COMMAND"; then
    log "deploy command failed"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if [[ -n "$POST_DEPLOY_HEALTHCHECK_URL" ]]; then
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "$POST_DEPLOY_HEALTHCHECK_URL" >/dev/null 2>&1; then
        log "healthcheck ok: ${POST_DEPLOY_HEALTHCHECK_URL}"
      else
        log "healthcheck failed: ${POST_DEPLOY_HEALTHCHECK_URL}"
      fi
    else
      log "curl not found, skip healthcheck"
    fi
  fi

  log "deploy finished"
  sleep "$INTERVAL_SECONDS"
done
