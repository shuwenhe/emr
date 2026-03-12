#!/usr/bin/env bash
# Build _simhash.cpython-*.so using pybind11 + OpenSSL
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${VENV_PY:-python3}"

PY_INCLUDE="$("$VENV_PY" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
PB_INCLUDE="$("$VENV_PY" -c 'import pybind11; print(pybind11.get_include())')"
EXT_SUFFIX="$("$VENV_PY" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"
OUTPUT="${SCRIPT_DIR}/_simhash${EXT_SUFFIX}"

echo "  PY_INCLUDE : $PY_INCLUDE"
echo "  PB_INCLUDE : $PB_INCLUDE"
echo "  EXT_SUFFIX : $EXT_SUFFIX"
echo "  OUTPUT     : $OUTPUT"

g++ -O3 -march=native -shared -fPIC -std=c++17 \
    -I"$PY_INCLUDE" -I"$PB_INCLUDE" \
    "${SCRIPT_DIR}/simhash.cpp" \
    -o "$OUTPUT" \
    -lssl -lcrypto

echo "Built: $OUTPUT"
