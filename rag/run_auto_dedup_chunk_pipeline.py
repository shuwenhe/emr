#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def run_cmd(cmd: List[str]) -> None:
    print("[run]", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def read_recommended_threshold(sweep_json: str) -> int:
    with open(sweep_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    t = data.get("recommended_threshold")
    if not isinstance(t, int):
        raise ValueError("recommended_threshold not found or invalid in sweep JSON")
    return t


def derive_base_name(path: str) -> str:
    name = Path(path).name
    if name.endswith(".jsonl"):
        return name[:-6]
    if name.endswith(".json"):
        return name[:-5]
    return name


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-click pipeline: threshold sweep -> dedup with recommended threshold -> chunk output."
        )
    )
    parser.add_argument("--docs-input", required=True, help="Input docs JSONL path")
    parser.add_argument("--output-dir", required=True, help="Directory for outputs")
    parser.add_argument(
        "--thresholds",
        default="2,3,4,5",
        help="Thresholds for sweep, comma-separated (default: 2,3,4,5)",
    )
    parser.add_argument(
        "--bands",
        type=int,
        default=4,
        help="Bands for SimHash lookup (must divide 64, default: 4)",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=80,
        help="Min text length for dedup/chunk (default: 80)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=600,
        help="Chunk size in chars (default: 600)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=100,
        help="Chunk overlap in chars (default: 100)",
    )
    parser.add_argument(
        "--limit-docs",
        type=int,
        default=None,
        help="Optional doc limit for quick test",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=20000,
        help="Progress print interval (default: 20000)",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Number of worker processes for SimHash precompute (default: 1)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Top N lines in markdown reports (default: 50)",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep all intermediate files (default keeps them anyway, reserved for future)",
    )
    args = parser.parse_args()

    docs_input = os.path.abspath(args.docs_input)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    sweep_script = os.path.join(script_dir, "simhash_threshold_sweep.py")
    dedup_script = os.path.join(script_dir, "dedup_docs_jsonl.py")
    chunk_script = os.path.join(script_dir, "docs_to_chunks_jsonl.py")
    report_script = os.path.join(script_dir, "dedup_report.py")

    base = derive_base_name(docs_input)

    sweep_json = os.path.join(output_dir, f"{base}.threshold_sweep.json")
    sweep_md = os.path.join(output_dir, f"{base}.threshold_sweep.md")

    dedup_docs = os.path.join(output_dir, f"{base}.dedup.jsonl")
    dup_log = os.path.join(output_dir, f"{base}.dup.jsonl")

    report_json = os.path.join(output_dir, f"{base}.dedup_report.json")
    report_md = os.path.join(output_dir, f"{base}.dedup_report.md")

    final_chunks = os.path.join(output_dir, f"{base}.chunks.final.jsonl")

    py = sys.executable

    # Step 1: Sweep thresholds.
    sweep_cmd = [
        py,
        sweep_script,
        "--input",
        docs_input,
        "--thresholds",
        args.thresholds,
        "--bands",
        str(args.bands),
        "--min-len",
        str(args.min_len),
        "--progress-every",
        str(args.progress_every),
        "--parallel-workers",
        str(args.parallel_workers),
        "--output-json",
        sweep_json,
        "--output-md",
        sweep_md,
    ]
    if args.limit_docs is not None:
        sweep_cmd.extend(["--limit-docs", str(args.limit_docs)])
    run_cmd(sweep_cmd)

    recommended_threshold = read_recommended_threshold(sweep_json)
    print(f"[info] recommended_threshold={recommended_threshold}", flush=True)

    # Step 2: Dedup using recommended threshold.
    dedup_cmd = [
        py,
        dedup_script,
        "--input",
        docs_input,
        "--output",
        dedup_docs,
        "--dup-output",
        dup_log,
        "--simhash-threshold",
        str(recommended_threshold),
        "--bands",
        str(args.bands),
        "--min-len",
        str(args.min_len),
        "--progress-every",
        str(args.progress_every),
        "--parallel-workers",
        str(args.parallel_workers),
    ]
    if args.limit_docs is not None:
        dedup_cmd.extend(["--limit-docs", str(args.limit_docs)])
    run_cmd(dedup_cmd)

    # Optional report for selected threshold.
    report_cmd = [
        py,
        report_script,
        "--docs",
        docs_input,
        "--dups",
        dup_log,
        "--output-json",
        report_json,
        "--output-md",
        report_md,
        "--top-n",
        str(args.top_n),
    ]
    run_cmd(report_cmd)

    # Step 3: Build final chunks from deduped docs.
    chunk_cmd = [
        py,
        chunk_script,
        "--input",
        dedup_docs,
        "--output",
        final_chunks,
        "--chunk-size",
        str(args.chunk_size),
        "--overlap",
        str(args.overlap),
        "--min-len",
        str(args.min_len),
    ]
    if args.limit_docs is not None:
        chunk_cmd.extend(["--limit-docs", str(args.limit_docs)])
    run_cmd(chunk_cmd)

    print("[done] pipeline finished", flush=True)
    print(f"[done] final_chunks={final_chunks}", flush=True)
    print(f"[done] dedup_docs={dedup_docs}", flush=True)
    print(f"[done] dup_log={dup_log}", flush=True)
    print(f"[done] sweep_json={sweep_json}", flush=True)
    print(f"[done] report_json={report_json}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
