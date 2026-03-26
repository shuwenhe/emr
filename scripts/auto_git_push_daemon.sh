#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INTERVAL_SECONDS="${AUTO_GIT_INTERVAL_SECONDS:-12}"
QUIET_SECONDS="${AUTO_GIT_QUIET_SECONDS:-8}"
AUTO_GIT_EXCLUDE_PATHS="${AUTO_GIT_EXCLUDE_PATHS:-.run/service.pid}"

cd "$REPO_DIR"

last_snapshot=""
changed_at=0

while true; do
  # Keep generated JSON in sync with JSONL source of truth.
  if [[ -f "$REPO_DIR/scripts/sync_kb_json_to_jsonl.sh" ]]; then
    bash "$REPO_DIR/scripts/sync_kb_json_to_jsonl.sh" >/dev/null 2>&1 || true
  fi

  # Skip auto-commit during merge conflicts.
  if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  status_args=(--porcelain -- .)
  read -r -a snapshot_excludes <<< "$AUTO_GIT_EXCLUDE_PATHS"
  for p in "${snapshot_excludes[@]}"; do
    [[ -z "$p" ]] && continue
    status_args+=(":(exclude)$p")
  done
  snapshot="$(git status "${status_args[@]}")"

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

  git_add_args=(-A --ignore-errors -- .)
  read -r -a exclude_paths <<< "$AUTO_GIT_EXCLUDE_PATHS"
  for p in "${exclude_paths[@]}"; do
    [[ -z "$p" ]] && continue
    git_add_args+=(":(exclude)$p")
  done
  git add "${git_add_args[@]}" || true

  if git diff --cached --quiet; then
    last_snapshot=""
    changed_at=0
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  # Build a concise English summary from staged diff (file list + first diff hunks).
  changed_files="$(
    {
      git diff --cached --name-only || true
    } | sed -n '1,20p' | tr '\n' ' ' | sed 's/ $//'
  )"
  diff_body="$(
    {
      git diff --cached --unified=0 -- '*.py' '*.ts' '*.tsx' '*.js' '*.sh' '*.go' 2>/dev/null || true
    } | sed -n '1,120p'
  )"
  prompt="You are a git commit message writer. Output ONLY a single commit message line with no extra text, no quotes, no markdown.

Format: <type>(<scope>): <short English description under 72 chars>
Types: feat, fix, refactor, chore, docs, style, perf
Scope: infer from changed files (e.g. rag, api, ui, ingestion, scripts)

Changed files: ${changed_files}

Diff (truncated):
${diff_body}

Commit message:"

  ai_msg=""
  if command -v ollama &>/dev/null; then
    ai_msg="$(echo "$prompt" | ollama run qwen3:1.7b --nowordwrap 2>/dev/null | tr -d '\r' | grep -m1 '.' | head -c 120 | sed 's/^[[:space:]]*//')"
  fi

  # Validate: must look like a conventional commit; fall back to file-list summary if not.
  if [[ -z "$ai_msg" ]] || ! echo "$ai_msg" | grep -qE '^(feat|fix|refactor|chore|docs|style|perf)\([a-zA-Z0-9_-]+\):'; then
    # Derive a readable summary from changed files
    first_file="$(git diff --cached --name-only | sed -n '1p')"
    scope="$(echo "$first_file" | cut -d/ -f1)"
    file_count="$(git diff --cached --name-only | wc -l | tr -d ' ')"
    if (( file_count == 1 )); then
      ai_msg="chore(${scope}): update $(basename "$first_file")"
    else
      ai_msg="chore(${scope}): update ${file_count} files (${changed_files:0:50})"
    fi
  fi

  commit_msg="${ai_msg} [$(date '+%Y-%m-%d %H:%M')]"
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
