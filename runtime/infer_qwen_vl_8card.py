#!/usr/bin/env python3
"""Distributed inference for Qwen2.5-VL on CANN/CUDA/CPU.

Input: JSONL with {"id": "...", "prompt": "..."}
Output: JSONL with {"id": "...", "response": "..."}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

import torch
import torch.distributed as dist
import transformers
from transformers import AutoProcessor

def resolve_model_cls():
    model_cls = getattr(transformers, "Qwen2_5_VLForConditionalGeneration", None)
    if model_cls is None:
        model_cls = getattr(transformers, "Qwen2VLForConditionalGeneration", None)
    if model_cls is None:
        model_cls = getattr(transformers, "AutoModelForVision2Seq", None)
    if model_cls is None:
        raise RuntimeError("No compatible Qwen VL loader found in transformers")
    return model_cls


@dataclass
class DistEnv:
    rank: int
    world_size: int
    local_rank: int
    device: torch.device
    runtime_backend: str


def _bool_from_str(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _can_use_cann() -> bool:
    try:
        import torch_npu  # noqa: F401

        return hasattr(torch, "npu")
    except Exception:
        return False


def _can_use_cuda() -> bool:
    try:
        return torch.cuda.is_available()
    except Exception:
        return False


def _resolve_runtime_backend(preferred: str) -> str:
    mode = preferred.strip().lower()
    if mode not in {"auto", "cann", "cuda", "cpu"}:
        raise ValueError(f"Unsupported runtime backend: {preferred}")

    if mode == "cann":
        if not _can_use_cann():
            raise RuntimeError("runtime_backend=cann but torch_npu/NPU is unavailable")
        return "cann"

    if mode == "cuda":
        if not _can_use_cuda():
            raise RuntimeError("runtime_backend=cuda but CUDA is unavailable")
        return "cuda"

    if mode == "cpu":
        return "cpu"

    if _can_use_cann():
        return "cann"
    if _can_use_cuda():
        return "cuda"
    return "cpu"


def init_dist(runtime_backend: str = "auto") -> DistEnv:
    rank = int(os.getenv("RANK", "0"))
    world_size = int(os.getenv("WORLD_SIZE", "1"))
    local_rank = int(os.getenv("LOCAL_RANK", "0"))

    resolved_backend = _resolve_runtime_backend(runtime_backend)

    if world_size > 1 and not dist.is_initialized():
        if resolved_backend == "cann":
            dist_backend = "hccl"
        elif resolved_backend == "cuda":
            dist_backend = "nccl"
        else:
            dist_backend = "gloo"
        dist.init_process_group(backend=dist_backend, rank=rank, world_size=world_size)

    if resolved_backend == "cann":
        torch.npu.set_device(local_rank)
        device = torch.device(f"npu:{local_rank}")
    elif resolved_backend == "cuda":
        torch.cuda.set_device(local_rank)
        device = torch.device(f"cuda:{local_rank}")
    else:
        device = torch.device("cpu")

    return DistEnv(
        rank=rank,
        world_size=world_size,
        local_rank=local_rank,
        device=device,
        runtime_backend=resolved_backend,
    )


def barrier_if_needed() -> None:
    if dist.is_available() and dist.is_initialized():
        dist.barrier()


def gather_objects(obj: Any, world_size: int) -> List[Any]:
    if dist.is_available() and dist.is_initialized() and world_size > 1:
        gathered: List[Any] = [None for _ in range(world_size)]
        dist.all_gather_object(gathered, obj)
        return gathered
    return [obj]


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Line {line_no} must be a JSON object")
            prompt = str(payload.get("prompt") or "").strip()
            if not prompt:
                raise ValueError(f"Line {line_no} missing non-empty 'prompt'")
            item_id = str(payload.get("id") or f"line-{line_no}")
            items.append({"id": item_id, "prompt": prompt, "_idx": len(items)})
    return items


def shard_items(items: List[Dict[str, Any]], rank: int, world_size: int) -> List[Dict[str, Any]]:
    return [item for i, item in enumerate(items) if i % world_size == rank]


def torch_dtype_from_name(name: str) -> torch.dtype:
    name = name.lower().strip()
    if name == "float16":
        return torch.float16
    if name == "bfloat16":
        return torch.bfloat16
    if name == "float32":
        return torch.float32
    raise ValueError(f"Unsupported dtype: {name}")


def _build_chat_text(processor: AutoProcessor, prompt: str) -> str:
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }
    ]
    return processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def generate_batch(
    model: Qwen2_5_VLForConditionalGeneration,
    processor: AutoProcessor,
    device: torch.device,
    prompts: List[str],
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> List[str]:
    texts = [_build_chat_text(processor, prompt) for prompt in prompts]

    inputs = processor(text=texts, images=None, videos=None, padding=True, return_tensors="pt")
    inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

    do_sample = temperature > 0
    gen_kwargs = {
        "max_new_tokens": max_new_tokens,
        "do_sample": do_sample,
        "temperature": max(temperature, 1e-5) if do_sample else 1.0,
        "top_p": top_p,
    }

    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)

    input_len = inputs["input_ids"].shape[1]
    completions = processor.batch_decode(
        output_ids[:, input_len:],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    return [text.strip() for text in completions]


def main() -> int:
    parser = argparse.ArgumentParser(description="Distributed Qwen2.5-VL inference on CANN/CUDA")
    parser.add_argument("--model-path", required=True, help="Local model dir")
    parser.add_argument("--input-file", required=True, help="JSONL input file")
    parser.add_argument("--output-file", required=True, help="Output JSONL file")
    parser.add_argument(
        "--runtime-backend",
        default=os.getenv("RUNTIME_BACKEND", "auto"),
        choices=["auto", "cann", "cuda", "cpu"],
    )
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])
    parser.add_argument("--trust-remote-code", default="true", help="true/false")
    args = parser.parse_args()

    env = init_dist(args.runtime_backend)
    is_main = env.rank == 0
    if is_main:
        print(
            f"[init] rank={env.rank} world_size={env.world_size} local_rank={env.local_rank} "
            f"runtime_backend={env.runtime_backend} device={env.device}",
            flush=True,
        )

    all_items = load_jsonl(args.input_file) if is_main else None
    if env.world_size > 1:
        holder = [all_items]
        dist.broadcast_object_list(holder, src=0)
        all_items = holder[0]
    if all_items is None:
        all_items = []

    local_items = shard_items(all_items, env.rank, env.world_size)

    dtype = torch_dtype_from_name(args.dtype)
    trust_remote_code = _bool_from_str(args.trust_remote_code)

    processor = AutoProcessor.from_pretrained(args.model_path, trust_remote_code=trust_remote_code)
    model_cls = resolve_model_cls()
    model = model_cls.from_pretrained(
        args.model_path,
        torch_dtype=dtype,
        trust_remote_code=trust_remote_code,
    )
    model = model.to(env.device)
    model.eval()

    local_results: List[Dict[str, Any]] = []
    for i in range(0, len(local_items), max(1, args.batch_size)):
        batch = local_items[i : i + max(1, args.batch_size)]
        outputs = generate_batch(
            model,
            processor,
            env.device,
            [item["prompt"] for item in batch],
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )
        for item, response in zip(batch, outputs):
            local_results.append(
                {
                    "id": item["id"],
                    "prompt": item["prompt"],
                    "response": response,
                    "_idx": item["_idx"],
                    "rank": env.rank,
                }
            )

    gathered = gather_objects(local_results, env.world_size)
    barrier_if_needed()

    if is_main:
        merged: List[Dict[str, Any]] = []
        for part in gathered:
            if isinstance(part, list):
                merged.extend(part)
        merged.sort(key=lambda x: x.get("_idx", 0))

        with open(args.output_file, "w", encoding="utf-8") as f:
            for item in merged:
                payload = {
                    "id": item["id"],
                    "prompt": item["prompt"],
                    "response": item["response"],
                    "rank": item["rank"],
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        print(f"[done] wrote {len(merged)} rows -> {args.output_file}", flush=True)

    barrier_if_needed()
    if dist.is_available() and dist.is_initialized():
        dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
