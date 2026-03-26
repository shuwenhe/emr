# EMR Dual Backend Inference (CANN + CUDA)

This directory provides a practical distributed inference pipeline for Qwen with two runtime stacks:

- CANN + Ascend NPU (HCCL)
- CUDA + NVIDIA GPU (NCCL)

## Files

- `infer_qwen_8card.py`: distributed inference entrypoint (auto/cann/cuda runtime)
- `launch_8card.sh`: one-command launcher for CANN/CUDA
- `prompts.example.jsonl`: input format example
- `requirements.txt`: Python dependencies

## Prerequisites

1. Model files are available locally (recommended), for example:
   - `/data/models/Qwen3-1.7B-Instruct`
2. For CANN mode: Ascend drivers + CANN + `torch_npu` are healthy.
3. For CUDA mode: CUDA drivers + compatible PyTorch are healthy.

## Input format

JSONL, one record per line:

```json
{"id":"1","prompt":"your prompt"}
```

Required fields:
- `prompt`: non-empty string

Optional fields:
- `id`: if missing, auto-generated

## Run

```bash
cd /app/emr/runtime
chmod +x launch_8card.sh
./launch_8card.sh /data/models/Qwen3-1.7B-Instruct ./prompts.example.jsonl ./outputs.jsonl auto
```

Force CANN mode:

```bash
RUNTIME_BACKEND=cann NPROC_PER_NODE=8 \
./launch_8card.sh /data/models/Qwen3-1.7B-Instruct ./prompts.example.jsonl ./outputs_cann.jsonl
```

Force CUDA mode:

```bash
RUNTIME_BACKEND=cuda CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 NPROC_PER_NODE=8 \
./launch_8card.sh /data/models/Qwen3-1.7B-Instruct ./prompts.example.jsonl ./outputs_cuda.jsonl
```

## Tunables

Environment variables:

- `ASCEND_RT_VISIBLE_DEVICES` (default `0,1,2,3,4,5,6,7`)
- `CUDA_VISIBLE_DEVICES` (default `0,1,2,3,4,5,6,7`)
- `RUNTIME_BACKEND` (`auto|cann|cuda|cpu`, default `auto`)
- `NPROC_PER_NODE` (default `8` for cann/cuda, `1` for cpu)
- `BATCH_SIZE` (default `4`)
- `MAX_NEW_TOKENS` (default `512`)
- `TEMPERATURE` (default `0.2`)
- `TOP_P` (default `0.9`)
- `DTYPE` (default `float16`, options: `float16|bfloat16|float32`)
- `MASTER_PORT` (default `29600`)

Example:

```bash
BATCH_SIZE=8 MAX_NEW_TOKENS=256 DTYPE=float16 \
./launch_8card.sh /data/models/Qwen3-1.7B-Instruct ./prompts.example.jsonl ./outputs.jsonl
```

## Notes

- This implementation uses throughput parallelism: each rank handles part of prompts and rank0 merges outputs.
- For CANN mode, distributed backend is HCCL. For CUDA mode, distributed backend is NCCL.
- If `auto` mode detects both stacks, CANN is preferred.
