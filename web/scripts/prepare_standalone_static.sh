#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

SRC_DIR="${WEB_DIR}/.next/static"
DST_DIR="${WEB_DIR}/.next/standalone/.next/static"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "[warn] missing source static dir: ${SRC_DIR}"
  exit 0
fi

mkdir -p "$(dirname "${DST_DIR}")"
rm -rf "${DST_DIR}"
cp -a "${SRC_DIR}" "${DST_DIR}"

echo "[ok] synced standalone static assets"
echo "[ok] from: ${SRC_DIR}"
echo "[ok] to  : ${DST_DIR}"
