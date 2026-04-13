#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

REMOTE="${AUTO_DEPLOY_REMOTE:-origin}"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
BRANCH="${AUTO_DEPLOY_BRANCH:-$CURRENT_BRANCH}"
INTERVAL_SECONDS="${AUTO_DEPLOY_INTERVAL_SECONDS:-20}"
ALLOW_DIRTY="${AUTO_DEPLOY_ALLOW_DIRTY:-0}"
LOCAL_CHANGES_MODE="${AUTO_DEPLOY_LOCAL_CHANGES:-0}"

# Default command deploys backend+web in production compose mode.
DEFAULT_DEPLOY_COMMAND='docker compose -f docker/docker-compose.prod.yml up -d --build web backend'
DEPLOY_COMMAND="${AUTO_DEPLOY_COMMAND:-}"
PRE_DEPLOY_COMMAND="${AUTO_DEPLOY_PRE_COMMAND:-}"
POST_DEPLOY_HEALTHCHECK_URL="${AUTO_DEPLOY_HEALTHCHECK_URL:-http://127.0.0.1:8000/healthz}"
CHUNK_HEALTHCHECK_URLS="${AUTO_DEPLOY_CHUNK_HEALTHCHECK_URLS:-}"
HEALTHCHECK_RETRIES="${AUTO_DEPLOY_HEALTHCHECK_RETRIES:-3}"
HEALTHCHECK_RETRY_DELAY_SECONDS="${AUTO_DEPLOY_HEALTHCHECK_RETRY_DELAY_SECONDS:-5}"

# Choose a safe default deploy command when AUTO_DEPLOY_COMMAND is not set:
# 1) Use docker compose if available and compose file exists.
# 2) Fallback to Makefile-managed backend restart for local dev/prod setups.
if [[ -z "$DEPLOY_COMMAND" ]]; then
  if command -v docker >/dev/null 2>&1 \
    && docker compose version >/dev/null 2>&1 \
    && [[ -f "docker/docker-compose.prod.yml" ]]; then
    DEPLOY_COMMAND="$DEFAULT_DEPLOY_COMMAND"
  else
    DEPLOY_COMMAND='make service-restart'
  fi
fi

log() {
  printf '[%s] [auto-deploy] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

run_deploy_once() {
  if [[ -n "$PRE_DEPLOY_COMMAND" ]]; then
    log "running pre-deploy command"
    if ! bash -lc "$PRE_DEPLOY_COMMAND"; then
      log "pre-deploy command failed"
      return 1
    fi
  fi

  log "running deploy command"
  if ! bash -lc "$DEPLOY_COMMAND"; then
    log "deploy command failed"
    return 1
  fi

  if [[ -n "$CHUNK_HEALTHCHECK_URLS" ]]; then
    if ! check_chunk_health "$CHUNK_HEALTHCHECK_URLS"; then
      log "chunk healthcheck failed after deploy, retry deploy command once"
      if ! bash -lc "$DEPLOY_COMMAND"; then
        log "retry deploy command failed"
        return 1
      fi
      if ! check_chunk_health "$CHUNK_HEALTHCHECK_URLS"; then
        log "chunk healthcheck still failing after retry deploy"
        return 1
      fi
    fi
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
  return 0
}

check_url_200() {
  local url="$1"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "$url" || true)"
  [[ "$code" == "200" ]]
}

check_chunk_health() {
  local raw_urls="$1"
  local normalized
  normalized="$(printf '%s' "$raw_urls" | tr ',' '\n' | sed '/^\s*$/d')"

  if [[ -z "$normalized" ]]; then
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    log "curl not found, skip chunk healthcheck"
    return 0
  fi

  local attempt url failed
  for ((attempt=1; attempt<=HEALTHCHECK_RETRIES; attempt++)); do
    failed=0
    while IFS= read -r url; do
      if ! check_url_200 "$url"; then
        log "chunk healthcheck failed (attempt ${attempt}/${HEALTHCHECK_RETRIES}): ${url}"
        failed=1
      else
        log "chunk healthcheck ok (attempt ${attempt}/${HEALTHCHECK_RETRIES}): ${url}"
      fi
    done <<< "$normalized"

    if [[ "$failed" -eq 0 ]]; then
      return 0
    fi

    if (( attempt < HEALTHCHECK_RETRIES )); then
      sleep "$HEALTHCHECK_RETRY_DELAY_SECONDS"
    fi
  done

  return 1
}

log "watching ${REMOTE}/${BRANCH} every ${INTERVAL_SECONDS}s"
log "deploy command: ${DEPLOY_COMMAND}"
log "local changes mode: ${LOCAL_CHANGES_MODE}"
if [[ -n "$CHUNK_HEALTHCHECK_URLS" ]]; then
  log "chunk healthcheck urls: ${CHUNK_HEALTHCHECK_URLS}"
fi
if [[ -n "$POST_DEPLOY_HEALTHCHECK_URL" ]]; then
  log "healthcheck url: ${POST_DEPLOY_HEALTHCHECK_URL}"
fi

last_local_snapshot="$(git status --porcelain || true)"

while true; do
  if [[ "$LOCAL_CHANGES_MODE" == "1" ]]; then
    current_snapshot="$(git status --porcelain || true)"
    if [[ "$current_snapshot" != "$last_local_snapshot" ]]; then
      log "local code change detected, starting deploy"
      if run_deploy_once; then
        last_local_snapshot="$current_snapshot"
      fi
    fi
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  # Protect local modifications from being overwritten by default.
  if [[ "$ALLOW_DIRTY" != "1" ]] && [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    log "tracked local changes detected, skip this cycle (set AUTO_DEPLOY_ALLOW_DIRTY=1 to override)"
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

  run_deploy_once || true
  sleep "$INTERVAL_SECONDS"
done
