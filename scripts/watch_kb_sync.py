#!/usr/bin/env python3
"""Watch knowledge_base.json/jsonl and keep them in sync."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch knowledge_base.json and knowledge_base.jsonl and keep them in sync."
    )
    parser.add_argument(
        "--repo-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root (default: project root)",
    )
    parser.add_argument(
        "--kb-json",
        default="./rag/kb/knowledge_base.json",
        help="Path to knowledge_base.json",
    )
    parser.add_argument(
        "--kb-jsonl",
        default="./rag/kb/knowledge_base.jsonl",
        help="Path to knowledge_base.jsonl",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable or "python3",
        help="Python executable used for sync helpers",
    )
    parser.add_argument(
        "--rebuild-command",
        default="make kb-build-structured",
        help="Optional rebuild command to run after jsonl changes",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Disable rebuild after jsonl changes",
    )
    return parser.parse_args()


def log(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[kb-watch][{ts}] {message}", flush=True)


def file_sig(path: Path) -> str:
    if not path.exists():
        return ""
    stat = path.stat()
    return f"{int(stat.st_mtime)}:{stat.st_size}"


def run_cmd(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def sync_jsonl_to_json(repo_dir: Path, kb_jsonl: Path, kb_json: Path, python_bin: str) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_dir}:{env.get('PYTHONPATH', '')}".rstrip(":")
    result = run_cmd(
        [
            python_bin,
            str(repo_dir / "scripts" / "kb_jsonl_to_json.py"),
            "--input-jsonl",
            str(kb_jsonl),
            "--output-json",
            str(kb_json),
        ],
        cwd=repo_dir,
        env=env,
    )
    if result.returncode == 0:
        if result.stdout.strip():
            log(result.stdout.strip())
        return True
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr.strip())
    return False


def sync_json_to_jsonl(repo_dir: Path, kb_json: Path, kb_jsonl: Path, python_bin: str) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_dir}:{env.get('PYTHONPATH', '')}".rstrip(":")
    result = run_cmd(
        [
            python_bin,
            str(repo_dir / "scripts" / "kb_json_to_jsonl.py"),
            "--input-json",
            str(kb_json),
            "--output-jsonl",
            str(kb_jsonl),
        ],
        cwd=repo_dir,
        env=env,
    )
    if result.returncode == 0:
        if result.stdout.strip():
            log(result.stdout.strip())
        return True
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr.strip())
    return False


def run_rebuild(repo_dir: Path, rebuild_command: str) -> bool:
    result = subprocess.run(
        rebuild_command,
        cwd=str(repo_dir),
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        log(f"rebuild completed: {rebuild_command}")
        return True
    log(f"rebuild failed: {rebuild_command}")
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr.strip())
    return False


def main() -> int:
    args = parse_args()
    repo_dir = Path(args.repo_dir).resolve()
    kb_json = Path(args.kb_json)
    if not kb_json.is_absolute():
        kb_json = (repo_dir / kb_json).resolve()
    kb_jsonl = Path(args.kb_jsonl)
    if not kb_jsonl.is_absolute():
        kb_jsonl = (repo_dir / kb_jsonl).resolve()

    log(f"starting watcher: json={kb_json} jsonl={kb_jsonl} interval={args.interval}s")

    last_json_sig = ""
    last_jsonl_sig = ""
    last_rebuilt_jsonl_sig = ""

    while True:
        json_sig = file_sig(kb_json)
        jsonl_sig = file_sig(kb_jsonl)

        if json_sig != last_json_sig or jsonl_sig != last_jsonl_sig:
            last_json_sig = json_sig
            last_jsonl_sig = jsonl_sig

            if kb_json.exists() and not kb_jsonl.exists():
                log("json exists without jsonl; syncing json -> jsonl")
                sync_json_to_jsonl(repo_dir, kb_json, kb_jsonl, args.python)
            elif kb_jsonl.exists() and not kb_json.exists():
                log("jsonl exists without json; syncing jsonl -> json")
                if sync_jsonl_to_json(repo_dir, kb_jsonl, kb_json, args.python):
                    last_rebuilt_jsonl_sig = file_sig(kb_jsonl)
            elif kb_json.exists() and kb_jsonl.exists():
                json_mtime = kb_json.stat().st_mtime
                jsonl_mtime = kb_jsonl.stat().st_mtime
                if json_mtime > jsonl_mtime:
                    log("detected json change; syncing json -> jsonl")
                    if sync_json_to_jsonl(repo_dir, kb_json, kb_jsonl, args.python):
                        last_jsonl_sig = file_sig(kb_jsonl)
                else:
                    log("detected jsonl change; syncing jsonl -> json")
                    if sync_jsonl_to_json(repo_dir, kb_jsonl, kb_json, args.python):
                        last_rebuilt_jsonl_sig = file_sig(kb_jsonl)

            current_jsonl_sig = file_sig(kb_jsonl)
            if not args.no_rebuild and current_jsonl_sig and current_jsonl_sig != last_rebuilt_jsonl_sig:
                log(f"rebuilding structured KB via: {args.rebuild_command}")
                if run_rebuild(repo_dir, args.rebuild_command):
                    last_rebuilt_jsonl_sig = current_jsonl_sig

        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
