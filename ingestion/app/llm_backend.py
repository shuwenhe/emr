from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def _env_int(name: str, default: int, *, min_value: Optional[int] = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw is not None else default
    except Exception:
        value = default
    if min_value is not None:
        return max(min_value, value)
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


BASE_DIR = Path(__file__).resolve().parents[2]


def _guess_runtime_model_path() -> str:
    env_model_path = os.getenv("MODEL_PATH", "").strip()
    if env_model_path and Path(env_model_path).exists():
        return env_model_path

    explicit_candidates = [
        "/data/models/Qwen3-1.7B-Instruct",
        "/data/models/Qwen2.5-1.5B-Instruct",
        "/data/models/Qwen2.5-7B-Instruct",
        "/data/models/Qwen2.5-14B-Instruct",
    ]
    for candidate in explicit_candidates:
        model_path = Path(candidate)
        if model_path.exists():
            return str(model_path)

    model_root = Path("/data/models")
    if model_root.exists():
        for child in sorted(model_root.iterdir()):
            name = child.name.lower()
            if child.is_dir() and "qwen" in name and (child / "config.json").exists():
                return str(child)
    return ""

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = _env_bool("OLLAMA_ENABLED", True)
OLLAMA_TIMEOUT_SEC = _env_int("OLLAMA_TIMEOUT_SEC", 60, min_value=5)
OLLAMA_MAX_RETRIES = _env_int("OLLAMA_MAX_RETRIES", 2, min_value=0)
OLLAMA_HEALTHCHECK_TIMEOUT_SEC = _env_int("OLLAMA_HEALTHCHECK_TIMEOUT_SEC", 2, min_value=1)
OLLAMA_UNAVAILABLE_COOLDOWN_SEC = _env_int("OLLAMA_UNAVAILABLE_COOLDOWN_SEC", 30, min_value=1)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "runtime").strip().lower()
LLM_RUNTIME_MODEL_PATH = os.getenv("LLM_RUNTIME_MODEL_PATH", _guess_runtime_model_path()).strip()
LLM_RUNTIME_SCRIPT = Path(
    os.getenv(
        "LLM_RUNTIME_SCRIPT",
        str(BASE_DIR / "runtime" / "infer_qwen_8card.py"),
    )
).resolve()
LLM_RUNTIME_PYTHON = os.getenv("LLM_RUNTIME_PYTHON", sys.executable).strip() or sys.executable
LLM_RUNTIME_BACKEND = os.getenv("LLM_RUNTIME_BACKEND", os.getenv("RUNTIME_BACKEND", "auto")).strip().lower()
LLM_RUNTIME_ENABLED = _env_bool("LLM_RUNTIME_ENABLED", bool(LLM_RUNTIME_MODEL_PATH))
LLM_RUNTIME_TIMEOUT_SEC = _env_int("LLM_RUNTIME_TIMEOUT_SEC", 900, min_value=30)
LLM_RUNTIME_DTYPE = os.getenv("LLM_RUNTIME_DTYPE", os.getenv("DTYPE", "float16")).strip() or "float16"
LLM_RUNTIME_TRUST_REMOTE_CODE = os.getenv("LLM_RUNTIME_TRUST_REMOTE_CODE", os.getenv("TRUST_REMOTE_CODE", "true"))
LLM_RUNTIME_NPU_LOGGING_ENABLED = _env_bool("LLM_RUNTIME_NPU_LOGGING_ENABLED", True)
LLM_RUNTIME_NPU_SAMPLING_SEC = _env_int("LLM_RUNTIME_NPU_SAMPLING_SEC", 5, min_value=1)

_OLLAMA_UNAVAILABLE_UNTIL_TS = 0.0
_OLLAMA_UNAVAILABLE_LOGGED_TS = 0.0
_AICORE_MEM_PATTERN = re.compile(r"\|\s*(\d{1,3})\s+\d+\s*/\s*\d+")


def _log_npu_smi(stage: str) -> None:
    if not LLM_RUNTIME_NPU_LOGGING_ENABLED:
        return
    if shutil.which("npu-smi") is None:
        logging.info("[NPU-SMI] stage=%s npu-smi=not-found", stage)
        return

    try:
        result = subprocess.run(
            ["npu-smi", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        logging.warning("[NPU-SMI] stage=%s failed=%s", stage, exc)
        return

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    process_present = "No running processes found" not in output
    aicore_values = [int(match.group(1)) for match in _AICORE_MEM_PATTERN.finditer(output)]
    aicore_nonzero = any(value > 0 for value in aicore_values)
    logging.info(
        "[NPU-SMI] stage=%s process_present=%s aicore_nonzero=%s sampled_cores=%s",
        stage,
        process_present,
        aicore_nonzero,
        aicore_values[:16],
    )


def _mark_ollama_unavailable(err: Exception) -> None:
    global _OLLAMA_UNAVAILABLE_UNTIL_TS, _OLLAMA_UNAVAILABLE_LOGGED_TS
    now = time.time()
    _OLLAMA_UNAVAILABLE_UNTIL_TS = now + OLLAMA_UNAVAILABLE_COOLDOWN_SEC
    if now >= _OLLAMA_UNAVAILABLE_LOGGED_TS:
        logging.warning(
            "Ollama unavailable, skip LLM calls for %ss model=%s base_url=%s err=%s",
            OLLAMA_UNAVAILABLE_COOLDOWN_SEC,
            OLLAMA_MODEL,
            OLLAMA_BASE_URL,
            err,
        )
        _OLLAMA_UNAVAILABLE_LOGGED_TS = _OLLAMA_UNAVAILABLE_UNTIL_TS


def _ollama_healthcheck() -> bool:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=OLLAMA_HEALTHCHECK_TIMEOUT_SEC) as response:
        return int(getattr(response, "status", 200) or 200) < 500


def _ollama_available() -> bool:
    if not OLLAMA_ENABLED:
        return False
    now = time.time()
    if now < _OLLAMA_UNAVAILABLE_UNTIL_TS:
        return False
    try:
        return _ollama_healthcheck()
    except Exception as exc:
        _mark_ollama_unavailable(exc)
        return False


def _runtime_available() -> bool:
    if not LLM_RUNTIME_ENABLED:
        return False
    if not LLM_RUNTIME_MODEL_PATH:
        return False
    if not Path(LLM_RUNTIME_MODEL_PATH).exists():
        return False
    if not LLM_RUNTIME_SCRIPT.exists():
        return False
    if not Path(LLM_RUNTIME_PYTHON).exists() and shutil.which(LLM_RUNTIME_PYTHON) is None:
        return False
    return True


def _resolve_provider() -> Optional[str]:
    provider = LLM_PROVIDER or "auto"
    if provider in {"0", "off", "false", "none", "disabled"}:
        return None
    if provider == "ollama":
        return "ollama" if OLLAMA_ENABLED else None
    if provider == "runtime":
        return "runtime" if _runtime_available() else None
    if provider != "auto":
        logging.warning("Unknown LLM_PROVIDER=%s, fallback to auto", provider)
    if _runtime_available():
        return "runtime"
    if OLLAMA_ENABLED:
        return "ollama"
    return None


def is_llm_enabled() -> bool:
    return _resolve_provider() is not None


def llm_provider_name() -> str:
    return _resolve_provider() or "disabled"


def llm_model_name() -> str:
    provider = _resolve_provider()
    if provider == "runtime":
        if not LLM_RUNTIME_MODEL_PATH:
            return "runtime"
        model_name = Path(LLM_RUNTIME_MODEL_PATH).name or LLM_RUNTIME_MODEL_PATH
        return f"runtime:{model_name}"
    if provider == "ollama":
        return OLLAMA_MODEL
    return ""


def llm_available() -> bool:
    provider = _resolve_provider()
    if provider == "runtime":
        return _runtime_available()
    if provider == "ollama":
        return _ollama_available()
    return False


def _ollama_generate(prompt: str, *, temperature: float, max_tokens: int) -> str:
    if not _ollama_available():
        return ""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    delay = 0.8
    last_exc: Optional[Exception] = None
    for attempt in range(OLLAMA_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SEC) as response:
                body = response.read().decode("utf-8")
            result = json.loads(body)
            return str(result.get("response") or "").strip()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < OLLAMA_MAX_RETRIES:
                logging.warning(
                    "Ollama generate retrying attempt=%d/%d timeout=%ss model=%s err=%s",
                    attempt + 1,
                    OLLAMA_MAX_RETRIES,
                    OLLAMA_TIMEOUT_SEC,
                    OLLAMA_MODEL,
                    exc,
                )
                time.sleep(delay)
                delay = min(delay * 2.0, 5.0)
                continue
    if isinstance(last_exc, Exception):
        _mark_ollama_unavailable(last_exc)
    if last_exc is not None:
        logging.error("Ollama generate error: %s: %s", type(last_exc).__name__, last_exc)
    logging.error(
        "Model: %s, URL: %s, timeout=%ss, retries=%s",
        OLLAMA_MODEL,
        OLLAMA_BASE_URL,
        OLLAMA_TIMEOUT_SEC,
        OLLAMA_MAX_RETRIES,
    )
    return ""


def _runtime_generate(prompt: str, *, temperature: float, max_tokens: int) -> str:
    if not _runtime_available():
        logging.warning(
            "Runtime LLM unavailable, script=%s model_path=%s enabled=%s",
            LLM_RUNTIME_SCRIPT,
            LLM_RUNTIME_MODEL_PATH,
            LLM_RUNTIME_ENABLED,
        )
        return ""

    with tempfile.TemporaryDirectory(prefix="emr-llm-runtime-") as tmpdir:
        tmp_path = Path(tmpdir)
        input_file = tmp_path / "input.jsonl"
        output_file = tmp_path / "output.jsonl"
        input_file.write_text(
            json.dumps({"id": "emr-llm", "prompt": prompt}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        command = [
            LLM_RUNTIME_PYTHON,
            str(LLM_RUNTIME_SCRIPT),
            "--model-path",
            LLM_RUNTIME_MODEL_PATH,
            "--input-file",
            str(input_file),
            "--output-file",
            str(output_file),
            "--runtime-backend",
            LLM_RUNTIME_BACKEND,
            "--batch-size",
            "1",
            "--max-new-tokens",
            str(max_tokens),
            "--temperature",
            str(temperature),
            "--top-p",
            "0.9",
            "--dtype",
            LLM_RUNTIME_DTYPE,
            "--trust-remote-code",
            LLM_RUNTIME_TRUST_REMOTE_CODE,
        ]
        env = os.environ.copy()
        env.setdefault("WORLD_SIZE", "1")
        env.setdefault("RANK", "0")
        env.setdefault("LOCAL_RANK", "0")

        try:
            process = subprocess.Popen(
                command,
                cwd=str(LLM_RUNTIME_SCRIPT.parent),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            logging.error("Runtime LLM launch failed backend=%s err=%s", LLM_RUNTIME_BACKEND, exc)
            return ""

        _log_npu_smi("runtime-start")

        started_at = time.time()
        stdout_data = ""
        stderr_data = ""
        timed_out = False
        sample_idx = 0
        while True:
            elapsed = time.time() - started_at
            remaining = max(0.0, float(LLM_RUNTIME_TIMEOUT_SEC) - elapsed)
            if remaining <= 0:
                timed_out = True
                process.kill()
                stdout_data, stderr_data = process.communicate()
                break

            wait_for = min(float(LLM_RUNTIME_NPU_SAMPLING_SEC), remaining)
            try:
                stdout_data, stderr_data = process.communicate(timeout=wait_for)
                break
            except subprocess.TimeoutExpired:
                sample_idx += 1
                _log_npu_smi(f"runtime-during-{sample_idx}")

        _log_npu_smi("runtime-end")

        if timed_out:
            logging.error(
                "Runtime LLM timeout backend=%s model=%s timeout=%ss",
                LLM_RUNTIME_BACKEND,
                llm_model_name(),
                LLM_RUNTIME_TIMEOUT_SEC,
            )
            if stdout_data:
                logging.error("Runtime LLM stdout before timeout: %s", stdout_data[-1000:])
            if stderr_data:
                logging.error("Runtime LLM stderr before timeout: %s", stderr_data[-1000:])
            return ""

        completed = process

        if completed.returncode != 0:
            logging.error(
                "Runtime LLM failed backend=%s model=%s code=%s",
                LLM_RUNTIME_BACKEND,
                llm_model_name(),
                completed.returncode,
            )
            if stdout_data:
                logging.error("Runtime LLM stdout: %s", stdout_data[-1000:])
            if stderr_data:
                logging.error("Runtime LLM stderr: %s", stderr_data[-1000:])
            return ""

        if not output_file.exists():
            logging.error("Runtime LLM completed without output file: %s", output_file)
            if stdout_data:
                logging.error("Runtime LLM stdout: %s", stdout_data[-1000:])
            return ""

        lines = [line.strip() for line in output_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return ""
        try:
            payload = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            logging.error("Runtime LLM output parse error: %s", exc)
            return ""
        return str(payload.get("response") or "").strip()


def llm_generate(prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
    provider = _resolve_provider()
    if provider == "runtime":
        return _runtime_generate(prompt, temperature=temperature, max_tokens=max_tokens)
    if provider == "ollama":
        return _ollama_generate(prompt, temperature=temperature, max_tokens=max_tokens)
    return ""