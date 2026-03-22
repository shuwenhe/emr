#!/bin/zsh

set -euo pipefail

REPO_DIR="/Users/feifei/emr"
LOG_DIR="/Users/feifei/Library/Logs"
LOG_FILE="${LOG_DIR}/emr-auto-commit.log"

mkdir -p "${LOG_DIR}"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] run"

  cd "${REPO_DIR}"

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "not a git repository"
    exit 1
  fi

  branch="$(git branch --show-current)"

  if [[ -z "${branch}" ]]; then
    echo "unable to determine current branch"
    exit 1
  fi

  if [[ -n "$(git status --porcelain)" ]]; then
    git add -A
    if [[ -n "$(git diff --cached --name-only)" ]]; then
      git commit -m "chore(emr): auto sync [$(date '+%Y-%m-%d %H:%M:%S')]"
      git push origin "${branch}"
      echo "pushed branch ${branch}"
    else
      echo "no staged changes after git add"
    fi
  else
    echo "no changes"
  fi
} >>"${LOG_FILE}" 2>&1
