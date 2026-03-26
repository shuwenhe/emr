#!/usr/bin/env bash
set -euo pipefail

# Example:
# ./launch_8card.sh /data/models/Qwen3-1.7B-Instruct ./prompts.jsonl ./outputs.jsonl

MODEL_PATH="${1:-}"
INPUT_FILE="${2:-}"
OUTPUT_FILE="${3:-}"
RUNTIME_BACKEND="${4:-${RUNTIME_BACKEND:-auto}}"

if [[ -z "$MODEL_PATH" || -z "$INPUT_FILE" || -z "$OUTPUT_FILE" ]]; then
  echo "Usage: $0 <model_path> <input_jsonl> <output_jsonl> [auto|cann|cuda|cpu]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export ASCEND_RT_VISIBLE_DEVICES="${ASCEND_RT_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HCCL_CONNECT_TIMEOUT="${HCCL_CONNECT_TIMEOUT:-1800}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"

if [[ "$RUNTIME_BACKEND" == "auto" ]]; then
  if command -v npu-smi >/dev/null 2>&1; then
    RUNTIME_BACKEND="cann"
  elif command -v nvidia-smi >/dev/null 2>&1; then
    RUNTIME_BACKEND="cuda"
  else
    RUNTIME_BACKEND="cpu"
  fi
fi

if [[ "$RUNTIME_BACKEND" == "cann" ]]; then
  NPROC_PER_NODE="${NPROC_PER_NODE:-8}"
elif [[ "$RUNTIME_BACKEND" == "cuda" ]]; then
  NPROC_PER_NODE="${NPROC_PER_NODE:-8}"
else
  NPROC_PER_NODE="${NPROC_PER_NODE:-1}"
fi

echo "[launcher] runtime_backend=${RUNTIME_BACKEND} nproc_per_node=${NPROC_PER_NODE}"

torchrun \
  --nproc_per_node="${NPROC_PER_NODE}" \
  --master_port="${MASTER_PORT:-29600}" \
  infer_qwen_8card.py \
  --model-path "$MODEL_PATH" \
  --input-file "$INPUT_FILE" \
  --output-file "$OUTPUT_FILE" \
  --runtime-backend "$RUNTIME_BACKEND" \
  --batch-size "${BATCH_SIZE:-4}" \
  --max-new-tokens "${MAX_NEW_TOKENS:-512}" \
  --temperature "${TEMPERATURE:-0.2}" \
  --top-p "${TOP_P:-0.9}" \
  --dtype "${DTYPE:-float16}" \
  --trust-remote-code "${TRUST_REMOTE_CODE:-true}"
