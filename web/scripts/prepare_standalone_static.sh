#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

SRC_DIR="${WEB_DIR}/.next/static"
DST_DIR_ROOT="${WEB_DIR}/.next/standalone/.next/static"
DST_DIR_NESTED="${WEB_DIR}/.next/standalone/web/.next/static"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "[warn] missing source static dir: ${SRC_DIR}"
  exit 0
fi

sync_static_dir() {
  local dst_dir="$1"
  mkdir -p "$(dirname "${dst_dir}")"
  rm -rf "${dst_dir}"
  cp -a "${SRC_DIR}" "${dst_dir}"
  echo "[ok] to  : ${dst_dir}"
}

sync_static_dir "${DST_DIR_ROOT}"

if [[ -d "${WEB_DIR}/.next/standalone/web/.next" ]]; then
  sync_static_dir "${DST_DIR_NESTED}"
fi

echo "[ok] synced standalone static assets"
echo "[ok] from: ${SRC_DIR}"
