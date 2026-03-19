#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "[auto-commit] Not inside a git repository."
  exit 1
fi

cd "$REPO_ROOT"

INTERVAL_SEC="${AUTO_COMMIT_INTERVAL_SEC:-5}"
COMMIT_PREFIX="${AUTO_COMMIT_MESSAGE_PREFIX:-chore(auto): code update}"
AUTO_PUSH_RAW="${AUTO_COMMIT_PUSH:-0}"
AUTO_PUSH_REMOTE="${AUTO_COMMIT_PUSH_REMOTE:-origin}"
AUTO_PUSH_BRANCH="${AUTO_COMMIT_PUSH_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"

is_true() {
  local raw="${1:-}"
  case "${raw,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

AUTO_PUSH_ENABLED=0
if is_true "$AUTO_PUSH_RAW"; then
  AUTO_PUSH_ENABLED=1
fi

# Code-like file extensions that can trigger auto commit.
CODE_EXT_RE='\.(py|go|js|jsx|ts|tsx|java|c|cc|cpp|h|hpp|rs|php|rb|swift|kt|kts|scala|sh|bash|zsh|sql|yaml|yml|json|toml|ini|cfg)$'

list_changed_files() {
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sed '/^$/d' | sort -u
}

is_code_file() {
  local file="$1"
  local base
  base="$(basename "$file")"

  if [[ "$file" =~ $CODE_EXT_RE ]]; then
    return 0
  fi

  case "$base" in
    Makefile|Dockerfile|.env|.env.example|.gitignore|.gitattributes|.dockerignore)
      return 0
      ;;
  esac

  if [[ "$file" =~ (^|/)Dockerfile(\.[^/]+)?$ ]]; then
    return 0
  fi
  if [[ "$file" =~ (^|/)Makefile$ ]]; then
    return 0
  fi

  return 1
}

has_code_changes() {
  local file
  while IFS= read -r file; do
    if is_code_file "$file"; then
      return 0
    fi
  done < <(list_changed_files)
  return 1
}

stage_code_changes() {
  local file
  while IFS= read -r file; do
    if is_code_file "$file"; then
      git add -- "$file" || true
    fi
  done < <(list_changed_files)
}

echo "[auto-commit] Started in $REPO_ROOT (interval=${INTERVAL_SEC}s, auto_push=${AUTO_PUSH_ENABLED}, push_remote=${AUTO_PUSH_REMOTE}, push_branch=${AUTO_PUSH_BRANCH})"

while true; do
  if has_code_changes; then
    stage_code_changes
    if ! git diff --cached --quiet; then
      ts="$(date '+%Y-%m-%d %H:%M:%S')"
      if git commit -m "${COMMIT_PREFIX} ${ts}" >/dev/null 2>&1; then
        echo "[auto-commit] committed at ${ts}"
        if [[ "$AUTO_PUSH_ENABLED" -eq 1 ]]; then
          if git push "$AUTO_PUSH_REMOTE" "$AUTO_PUSH_BRANCH" >/dev/null 2>&1; then
            echo "[auto-commit] pushed to ${AUTO_PUSH_REMOTE}/${AUTO_PUSH_BRANCH} at ${ts}"
          else
            echo "[auto-commit] push failed: ${AUTO_PUSH_REMOTE}/${AUTO_PUSH_BRANCH}"
          fi
        fi
      fi
    fi
  fi
  sleep "$INTERVAL_SEC"
done
