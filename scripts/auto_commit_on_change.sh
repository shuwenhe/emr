#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "[auto-commit] Not inside a git repository."
  exit 1
fi

cd "$REPO_ROOT"

INTERVAL_SEC="${AUTO_COMMIT_INTERVAL_SEC:-5}"
COMMIT_SCOPE="${AUTO_COMMIT_SCOPE:-auto}"
COMMIT_TYPE_RAW="${AUTO_COMMIT_TYPE:-}"
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
CODE_EXT_RE='\.(py|go|js|jsx|ts|tsx|java|c|cc|cpp|h|hpp|rs|php|rb|swift|kt|kts|scala|sh|bash|zsh|sql|yaml|yml|json|jsonl|toml|ini|cfg)$'

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

contains_line() {
  local needle="$1"
  local text="$2"
  grep -Fqx "$needle" <<< "$text"
}

summarize_area_from_file() {
  local file="$1"
  case "$file" in
    ingestion/app/*)
      echo "Improve ingestion and AI report generation pipeline"
      ;;
    route/*)
      echo "Refine API routing and persistence flow"
      ;;
    reports/python/*)
      echo "Enhance report rendering and output content"
      ;;
    rag/*)
      echo "Enhance RAG retrieval and knowledge base workflow"
      ;;
    scripts/*)
      echo "Improve automation scripts and developer tooling"
      ;;
    web/*)
      echo "Update web application behavior and assets"
      ;;
    config/*)
      echo "Adjust project configuration defaults"
      ;;
    Makefile|*/Makefile)
      echo "Update build and automation tasks"
      ;;
    Dockerfile|*/Dockerfile|Dockerfile.*|*/Dockerfile.*)
      echo "Adjust container build/runtime setup"
      ;;
    .env|.env.example)
      echo "Update environment variable templates"
      ;;
    *)
      echo "Update project source files"
      ;;
  esac
}

resolve_commit_type() {
  local files="$1"
  local lowered="${files,,}"
  local forced="${COMMIT_TYPE_RAW,,}"

  if [[ "$forced" == "feat" || "$forced" == "fix" ]]; then
    echo "$forced"
    return
  fi

  if [[ "$lowered" =~ (fix|bug|hotfix|patch|issue|error) ]]; then
    echo "fix"
    return
  fi

  echo "feat"
}

build_commit_message() {
  local files
  files="$(git diff --cached --name-only | sed '/^$/d')"
  if [[ -z "$files" ]]; then
    echo "feat(${COMMIT_SCOPE}): summarize code updates"
    echo "Main changes:\n- No staged file summary available."
    return
  fi

  local feature_lines=""
  local file_lines=""
  local feature_count=0
  local file_count=0
  local file

  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    file_count=$((file_count + 1))

    local feature
    feature="$(summarize_area_from_file "$file")"
    if ! contains_line "$feature" "$feature_lines"; then
      feature_lines+="$feature"$'\n'
      feature_count=$((feature_count + 1))
    fi

    # Keep the body concise.
    if [[ "$file_count" -le 12 ]]; then
      file_lines+="- ${file}"$'\n'
    fi
  done <<< "$files"

  local commit_type
  commit_type="$(resolve_commit_type "$files")"

  local subject
  subject="${commit_type}(${COMMIT_SCOPE}): summarize code updates (${file_count} files, ${feature_count} areas)"

  local body="Main changes:\n"
  local feature
  while IFS= read -r feature; do
    [[ -z "$feature" ]] && continue
    body+="- ${feature}\n"
  done <<< "$feature_lines"

  body+="\nTouched files:\n${file_lines}"
  if [[ "$file_count" -gt 12 ]]; then
    body+="- ... and additional files\n"
  fi

  echo "$subject"
  echo -e "$body"
}

echo "[auto-commit] Started in $REPO_ROOT (interval=${INTERVAL_SEC}s, auto_push=${AUTO_PUSH_ENABLED}, push_remote=${AUTO_PUSH_REMOTE}, push_branch=${AUTO_PUSH_BRANCH})"

while true; do
  if has_code_changes; then
    stage_code_changes
    if ! git diff --cached --quiet; then
      ts="$(date '+%Y-%m-%d %H:%M:%S')"
      commit_subject=""
      commit_body=""
      mapfile -t commit_parts < <(build_commit_message)
      commit_subject="${commit_parts[0]:-feat(${COMMIT_SCOPE}): summarize code updates}"
      if [[ "${#commit_parts[@]}" -gt 1 ]]; then
        commit_body="${commit_parts[1]}"
      fi

      if [[ -n "$commit_body" ]]; then
        if git commit -m "$commit_subject" -m "$commit_body" >/dev/null 2>&1; then
          echo "[auto-commit] committed at ${ts}: $commit_subject"
          if [[ "$AUTO_PUSH_ENABLED" -eq 1 ]]; then
            if git push "$AUTO_PUSH_REMOTE" "$AUTO_PUSH_BRANCH" >/dev/null 2>&1; then
              echo "[auto-commit] pushed to ${AUTO_PUSH_REMOTE}/${AUTO_PUSH_BRANCH} at ${ts}"
            else
              echo "[auto-commit] push failed: ${AUTO_PUSH_REMOTE}/${AUTO_PUSH_BRANCH}"
            fi
          fi
        fi
      elif git commit -m "$commit_subject" >/dev/null 2>&1; then
        echo "[auto-commit] committed at ${ts}: $commit_subject"
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
