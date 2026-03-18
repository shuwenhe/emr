#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INTERVAL_SECONDS="${AUTO_GIT_INTERVAL_SECONDS:-12}"
QUIET_SECONDS="${AUTO_GIT_QUIET_SECONDS:-8}"

cd "$REPO_DIR"

last_snapshot=""
changed_at=0

while true; do
  # Skip auto-commit during merge conflicts.
  if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  snapshot="$(git status --porcelain)"

  if [[ -z "$snapshot" ]]; then
    last_snapshot=""
    changed_at=0
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  now="$(date +%s)"

  if [[ "$snapshot" != "$last_snapshot" ]]; then
    last_snapshot="$snapshot"
    changed_at="$now"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if (( now - changed_at < QUIET_SECONDS )); then
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  git add -A

  if git diff --cached --quiet; then
    last_snapshot=""
    changed_at=0
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  commit_msg="chore(auto): sync changes $(date '+%Y-%m-%d %H:%M:%S')"
  if ! git commit -m "$commit_msg"; then
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  branch="$(git branch --show-current)"
  if ! git push origin "$branch"; then
    # Keep running; next cycles will retry on new commits.
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  last_snapshot=""
  changed_at=0
  sleep "$INTERVAL_SECONDS"
done
