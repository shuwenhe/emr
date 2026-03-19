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
  [[ "$file" =~ $CODE_EXT_RE ]]
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

echo "[auto-commit] Started in $REPO_ROOT (interval=${INTERVAL_SEC}s)"

while true; do
  if has_code_changes; then
    stage_code_changes
    if ! git diff --cached --quiet; then
      ts="$(date '+%Y-%m-%d %H:%M:%S')"
      git commit -m "${COMMIT_PREFIX} ${ts}" >/dev/null 2>&1 || true
      if git rev-parse --verify HEAD >/dev/null 2>&1; then
        echo "[auto-commit] committed at ${ts}"
      fi
    fi
  fi
  sleep "$INTERVAL_SEC"
done
