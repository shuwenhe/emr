from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import faiss
from tqdm import tqdm

from .docx_parser import blocks_from_text, parse_docx, parse_docx_with_markdown
from .embeddings import build_embeddings
from .kb_utils import (
    is_low_signal_text,
    iter_batches,
    normalize_text,
    safe_relpath,
    sanitize_embedding_text_aggressive,
    sanitize_embedding_text,
    sha1_file,
    sha1_text,
    split_list_items,
    split_text,
    table_to_linearized_text,
    table_to_markdown,
)
from .schemas import ChunkRecord, Manifest


DOC_EXTENSIONS = {".doc", ".docx"}


class UserAbort(Exception):
    pass


def _is_word_lock(name: str) -> bool:
    return name.startswith("~$")


_STEP_TITLE_ZH = {
    "Scanning source documents": "扫描源文档",
    "Confirming rebuild": "确认是否重建知识库",
    "Preparing output directories": "准备输出目录",
    "Parsing documents into chunks": "解析文档并切分为分块",
    "Initializing embedding model": "初始化嵌入模型",
    "Embedding chunks": "为分块生成向量",
    "Building FAISS index": "构建 FAISS 索引",
    "Writing KB artifacts and activating version": "写入知识库产物并激活版本",
}


def _log_step(step: int, total_steps: int, title: str, detail: Optional[str] = None) -> None:
    message = f"Step {step}/{total_steps}: {title}"
    if detail:
        message = f"{message} | {detail}"
    print(message)
    zh_title = _STEP_TITLE_ZH.get(title, title)
    zh_message = f"第 {step}/{total_steps} 步：{zh_title}"
    if detail:
        zh_message = f"{zh_message} | {detail}"
    print(zh_message)


def _format_bytes_gib(value_bytes: int) -> str:
    gib = float(value_bytes) / float(1024**3)
    return f"{gib:.2f}GiB"


def _read_proc_stat_total_idle() -> Tuple[int, int]:
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        first = handle.readline().strip().split()
    if len(first) < 8 or first[0] != "cpu":
        raise RuntimeError("invalid /proc/stat format")
    values = [int(item) for item in first[1:]]
    total = sum(values)
    idle = values[3] + values[4]
    return total, idle


def _read_process_cpu_ticks() -> Tuple[int, int]:
    with open("/proc/self/stat", "r", encoding="utf-8") as handle:
        data = handle.read().strip()
    # /proc/self/stat: fields after ')' are space-separated.
    # utime/stime are 14/15, cutime/cstime are 16/17.
    right = data.rsplit(")", 1)[-1].strip().split()
    if len(right) < 15:
        raise RuntimeError("invalid /proc/self/stat format")
    utime = int(right[11])
    stime = int(right[12])
    cutime = int(right[13])
    cstime = int(right[14])
    self_ticks = utime + stime
    total_ticks = self_ticks + cutime + cstime
    return self_ticks, total_ticks


def _read_memory_stats() -> Tuple[int, int, int]:
    total_kb = 0
    available_kb = 0
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
            if total_kb and available_kb:
                break
    if total_kb <= 0:
        raise RuntimeError("MemTotal missing in /proc/meminfo")
    used_kb = max(total_kb - available_kb, 0)

    with open("/proc/self/statm", "r", encoding="utf-8") as handle:
        parts = handle.readline().strip().split()
    rss_pages = int(parts[1]) if len(parts) > 1 else 0
    page_size = os.sysconf("SC_PAGE_SIZE")
    rss_bytes = rss_pages * page_size
    return total_kb * 1024, used_kb * 1024, rss_bytes


def _read_gpu_stats() -> List[Dict[str, Any]]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
    except Exception:
        return []
    if proc.returncode != 0:
        return []

    out: List[Dict[str, Any]] = []
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            mem_used_mib = int(float(parts[3]))
            mem_total_mib = int(float(parts[4]))
            mem_pct = 0.0
            if mem_total_mib > 0:
                mem_pct = (mem_used_mib * 100.0) / mem_total_mib
            out.append(
                {
                    "index": parts[0],
                    "name": parts[1],
                    "util_pct": float(parts[2]),
                    "mem_used_mib": mem_used_mib,
                    "mem_total_mib": mem_total_mib,
                    "mem_pct": mem_pct,
                }
            )
        except ValueError:
            continue
    return out


def _start_resource_monitor(tag: str) -> Callable[[], None]:
    interval = max(0, int(os.getenv("RAG_RESOURCE_METRICS_SEC", "5")))
    if interval <= 0:
        return lambda: None
    gpu_enabled = _env_flag("RAG_RESOURCE_LOG_GPU", default=True)
    stop = threading.Event()
    done = threading.Event()

    def _loop() -> None:
        cpu_count = max(1, os.cpu_count() or 1)
        try:
            prev_total, prev_idle = _read_proc_stat_total_idle()
            prev_self, prev_proc_total = _read_process_cpu_ticks()
        except Exception:
            prev_total, prev_idle, prev_self, prev_proc_total = 0, 0, 0, 0

        while not stop.wait(interval):
            try:
                now_total, now_idle = _read_proc_stat_total_idle()
                now_self, now_proc_total = _read_process_cpu_ticks()
                delta_total = max(now_total - prev_total, 1)
                delta_idle = max(now_idle - prev_idle, 0)
                delta_self = max(now_self - prev_self, 0)
                delta_proc_total = max(now_proc_total - prev_proc_total, 0)

                cpu_pct = max(0.0, min(100.0, (1.0 - (delta_idle / delta_total)) * 100.0))
                proc_cpu_self_pct = max(0.0, (delta_self / delta_total) * 100.0 * cpu_count)
                proc_cpu_total_pct = max(0.0, (delta_proc_total / delta_total) * 100.0 * cpu_count)
                proc_cpu_total_of_host_pct = max(0.0, proc_cpu_total_pct / cpu_count)

                total_mem_b, used_mem_b, rss_b = _read_memory_stats()
                mem_pct = 0.0
                if total_mem_b > 0:
                    mem_pct = (used_mem_b * 100.0) / total_mem_b

                msg = (
                    f"[RESOURCE_METRIC] tag={tag} "
                    f"cpu={cpu_pct:.1f}% "
                    f"proc_cpu_self={proc_cpu_self_pct:.1f}% proc_cpu_total={proc_cpu_total_pct:.1f}% "
                    f"proc_cpu_total_of_host={proc_cpu_total_of_host_pct:.1f}% "
                    f"mem={_format_bytes_gib(used_mem_b)}/{_format_bytes_gib(total_mem_b)}({mem_pct:.1f}%) "
                    f"proc_mem={_format_bytes_gib(rss_b)}"
                )
                if gpu_enabled:
                    gpus = _read_gpu_stats()
                    if gpus:
                        gpu_parts = []
                        for gpu in gpus:
                            gpu_parts.append(
                                f"gpu{gpu['index']}:{gpu['util_pct']:.1f}% "
                                f"mem={gpu['mem_used_mib']}MiB/{gpu['mem_total_mib']}MiB({gpu['mem_pct']:.1f}%)"
                            )
                        msg = msg + " | " + " ; ".join(gpu_parts)
                    else:
                        msg = msg + " | gpu=unavailable"

                tqdm.write(msg)
                prev_total, prev_idle = now_total, now_idle
                prev_self, prev_proc_total = now_self, now_proc_total
            except Exception as exc:  # noqa: BLE001
                tqdm.write(f"[RESOURCE_METRIC] tag={tag} monitor_error={exc}")

        done.set()

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()

    def _stop() -> None:
        stop.set()
        done.wait(timeout=1.0)

    return _stop

# ── Go-based concurrent embedder ──────────────────────────────────────────────

GO_EMBEDDER_BIN = os.path.join(os.path.dirname(__file__), "go_embedder")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class EmbedMetrics:
    backend: str
    requested_chunks: int
    batch_size: int
    batch_count: int = 0
    failed_batches: int = 0
    kept_chunks: int = 0
    failed_chunks: int = 0
    total_batch_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        avg_batch_ms = 0.0
        if self.batch_count > 0:
            avg_batch_ms = (self.total_batch_seconds / self.batch_count) * 1000
        return {
            "backend": self.backend,
            "requested_chunks": self.requested_chunks,
            "batch_size": self.batch_size,
            "batch_count": self.batch_count,
            "failed_batches": self.failed_batches,
            "kept_chunks": self.kept_chunks,
            "failed_chunks": self.failed_chunks,
            "total_batch_seconds": round(self.total_batch_seconds, 4),
            "avg_batch_ms": round(avg_batch_ms, 2),
        }


def _find_go_embedder() -> Optional[str]:
    """Return path to the compiled Go embedder binary, or None if unavailable."""
    if os.path.isfile(GO_EMBEDDER_BIN) and os.access(GO_EMBEDDER_BIN, os.X_OK):
        return GO_EMBEDDER_BIN
    return None


class GoEmbedder:
    """Drop-in replacement for LangChain embeddings that delegates to the Go
    concurrent embedder subprocess.  Matches the embed_documents() interface."""

    def __init__(
        self,
        binary: str,
        provider: str,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        concurrency: int = 8,
    ) -> None:
        env = os.environ.copy()
        env["EMBED_PROVIDER"] = provider
        env["EMBED_MODEL"] = model
        env["EMBED_CONCURRENCY"] = str(concurrency)
        if base_url:
            if provider == "ollama":
                env["OLLAMA_BASE_URL"] = base_url
            else:
                env["OPENAI_BASE_URL"] = base_url
        if api_key:
            env["OPENAI_API_KEY"] = api_key

        self._proc = subprocess.Popen(
            [binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            env=env,
        )
        self._stdin = io.TextIOWrapper(self._proc.stdin, encoding="utf-8")   # type: ignore[arg-type]
        self._stdout = io.TextIOWrapper(self._proc.stdout, encoding="utf-8") # type: ignore[arg-type]
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: Dict[int, Dict[str, Any]] = {}
        self._next_id = 0
        self._closed = False
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()

    def _reader_loop(self) -> None:
        try:
            while True:
                raw = self._stdout.readline()
                if not raw:
                    break
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                batch_id = result.get("id")
                if not isinstance(batch_id, int):
                    continue
                with self._pending_lock:
                    slot = self._pending.get(batch_id)
                    if not slot:
                        continue
                    slot["payload"] = result
                    slot["event"].set()
        finally:
            self._fail_all_pending("Go embedder process closed unexpectedly")

    def _fail_all_pending(self, message: str) -> None:
        with self._pending_lock:
            for slot in self._pending.values():
                if "payload" not in slot:
                    slot["payload"] = {"error": message}
                slot["event"].set()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Send one batch and wait for the matching response. Thread-safe and concurrent."""
        if self._closed:
            raise RuntimeError("Go embedder is closed")

        event = threading.Event()
        with self._pending_lock:
            batch_id = self._next_id
            self._next_id += 1
            self._pending[batch_id] = {"event": event}

        try:
            line = json.dumps({"id": batch_id, "texts": texts}, ensure_ascii=False)
            with self._write_lock:
                self._stdin.write(line + "\n")
                self._stdin.flush()
        except Exception:  # noqa: BLE001
            with self._pending_lock:
                self._pending.pop(batch_id, None)
            raise

        while not event.wait(timeout=0.5):
            if self._proc.poll() is not None:
                self._fail_all_pending("Go embedder process terminated")
                break

        with self._pending_lock:
            slot = self._pending.pop(batch_id, None)
        if not slot or "payload" not in slot:
            raise RuntimeError("Go embedder returned no response for batch")
        payload = slot["payload"]
        if "error" in payload:
            raise RuntimeError(f"Go embedder error: {payload['error']}")
        return payload["vectors"]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            with self._write_lock:
                self._stdin.write("\n")  # blank line = EOF signal
                self._stdin.flush()
                self._stdin.close()
            self._proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self._proc.kill()
        finally:
            self._fail_all_pending("Go embedder closed")
            if hasattr(self, "_reader") and self._reader.is_alive():
                self._reader.join(timeout=1)

    def __del__(self) -> None:
        self.close()


# ── document scanning ─────────────────────────────────────────────────────────


def scan_documents(source_dir: str) -> Tuple[List[str], List[Dict[str, str]]]:
    included: List[str] = []
    skipped: List[Dict[str, str]] = []
    for root, _, files in os.walk(source_dir):
        for filename in files:
            if _is_word_lock(filename):
                skipped.append({"path": os.path.join(root, filename), "reason": "word_lock"})
                continue
            ext = os.path.splitext(filename)[1].lower()
            path = os.path.join(root, filename)
            try:
                if os.path.getsize(path) == 0:
                    skipped.append({"path": path, "reason": "empty_file"})
                    continue
            except OSError:
                skipped.append({"path": path, "reason": "stat_failed"})
                continue
            if ext in DOC_EXTENSIONS:
                included.append(path)
            else:
                skipped.append({"path": path, "reason": "unsupported_extension"})
    return included, skipped


def _which_binary(candidates: Iterable[str]) -> Optional[str]:
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _expected_docx_path(path: str, output_dir: str) -> str:
    filename = os.path.basename(path)
    stem = os.path.splitext(filename)[0]
    return os.path.join(output_dir, f"{stem}.docx")


def _convert_doc_with_unstructured(path: str, output_dir: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        from unstructured.partition.common.common import convert_office_doc
    except ImportError:
        return None, "unstructured_missing"
    if not _which_binary(["soffice"]):
        return None, "soffice_missing"
    try:
        convert_office_doc(
            path,
            output_dir,
            target_format="docx",
            target_filter="MS Word 2007 XML",
        )
    except Exception:
        return None, "doc_convert_failed_unstructured"
    converted = _expected_docx_path(path, output_dir)
    if os.path.exists(converted):
        return converted, None
    return None, "doc_convert_failed_unstructured"


def _convert_doc_with_soffice(path: str, output_dir: str) -> Tuple[Optional[str], Optional[str]]:
    binary = _which_binary(["soffice", "libreoffice"])
    if not binary:
        return None, "soffice_missing"
    cmd = [
        binary,
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        output_dir,
        path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        return None, "doc_convert_failed_soffice"
    converted = _expected_docx_path(path, output_dir)
    if os.path.exists(converted):
        return converted, None
    return None, "doc_convert_failed_soffice"


def _convert_doc_with_textutil(path: str, output_dir: str) -> Tuple[Optional[str], Optional[str]]:
    textutil = _which_binary(["textutil"])
    if not textutil:
        return None, "textutil_missing"
    cmd = [textutil, "-convert", "docx", "-output", output_dir, path]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "doc_convert_timeout_textutil"
    if result.returncode != 0:
        return None, "doc_convert_failed_textutil"
    converted = _expected_docx_path(path, output_dir)
    if os.path.exists(converted):
        return converted, None
    return None, "doc_convert_failed_textutil"


def _extract_doc_text_with_antiword(path: str) -> Tuple[Optional[str], Optional[str]]:
    antiword = _which_binary(["antiword"])
    if not antiword:
        return None, "antiword_missing"
    try:
        result = subprocess.run(
            [antiword, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None, "antiword_timeout"
    if result.returncode != 0:
        return None, "antiword_failed"
    return result.stdout, None


def convert_doc_to_docx(path: str, output_dir: str) -> Tuple[Optional[str], Optional[str]]:
    converted, reason = _convert_doc_with_unstructured(path, output_dir)
    if converted:
        return converted, None

    converted, reason = _convert_doc_with_soffice(path, output_dir)
    if converted:
        return converted, None

    converted, reason = _convert_doc_with_textutil(path, output_dir)
    if converted:
        return converted, None

    return None, reason or "doc_convert_failed"


def _build_chunk_id(file_path: str, doc_hash: str, chunk_index: int, chunk_type: str) -> str:
    return sha1_text(f"{file_path}:{doc_hash}:{chunk_type}:{chunk_index}")


def _title_prefix(title_path: List[str]) -> str:
    cleaned = [part for part in title_path if part]
    if not cleaned:
        return ""
    return " > ".join(cleaned)


def _attach_title_prefix(title_path: List[str], text: str) -> str:
    prefix = _title_prefix(title_path)
    if not prefix:
        return text
    return f"{prefix}\n{text}"


def _find_repeated_short_paragraphs(
    blocks,
    max_len: int = 40,
    min_count: int = 3,
) -> set:
    counts: Dict[str, int] = {}
    for block in blocks:
        if block.block_type != "paragraph":
            continue
        text = normalize_text(block.text)
        if not text or len(text) > max_len:
            continue
        counts[text] = counts.get(text, 0) + 1
    return {text for text, count in counts.items() if count >= min_count}


def _shorten(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _checkpoint_signature(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return sha1_text(raw)


def _load_embedding_checkpoint(
    checkpoint_dir: str,
    signature: str,
) -> Tuple[Dict[str, Tuple[ChunkRecord, List[float]]], List[Dict[str, str]], int]:
    state_path = os.path.join(checkpoint_dir, "state.json")
    embedded_path = os.path.join(checkpoint_dir, "embedded.jsonl")
    failed_path = os.path.join(checkpoint_dir, "failed.jsonl")
    if not os.path.exists(state_path) or not os.path.exists(embedded_path):
        return {}, [], 0

    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception:
        return {}, [], 0

    if str(state.get("signature") or "") != signature:
        return {}, [], 0

    embedded_map: Dict[str, Tuple[ChunkRecord, List[float]]] = {}
    loaded = 0
    try:
        with open(embedded_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                record = ChunkRecord.model_validate(row.get("record") or {})
                vector = row.get("vector")
                if not isinstance(vector, list) or not vector:
                    continue
                embedded_map[record.chunk_id] = (record, vector)
                loaded += 1
    except Exception:
        return {}, [], 0

    failed: List[Dict[str, str]] = []
    if os.path.exists(failed_path):
        try:
            with open(failed_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if isinstance(row, dict):
                        failed.append({
                            "chunk_id": str(row.get("chunk_id") or ""),
                            "file_path": str(row.get("file_path") or ""),
                            "reason": str(row.get("reason") or ""),
                        })
        except Exception:
            failed = []
    return embedded_map, failed, loaded


def _write_checkpoint_state(
    checkpoint_dir: str,
    signature: str,
    payload: Dict[str, Any],
) -> None:
    os.makedirs(checkpoint_dir, exist_ok=True)
    state_path = os.path.join(checkpoint_dir, "state.json")
    tmp_path = state_path + ".tmp"
    body = {"signature": signature, **payload}
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(body, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, state_path)


def _append_checkpoint_rows(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_partial_snapshot(
    partial_dir: str,
    records: List[ChunkRecord],
    vectors: List[List[float]],
    kb_version: str,
    source_dir: str,
    embed_model: str,
    provider: str,
    failed_items: List[Dict[str, str]],
) -> None:
    if not records or not vectors:
        return
    os.makedirs(partial_dir, exist_ok=True)

    for idx, record in enumerate(records):
        record.vector_id = idx

    vector_array = np.array(vectors, dtype="float32")
    faiss.normalize_L2(vector_array)
    dim = vector_array.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vector_array)
    faiss.write_index(index, os.path.join(partial_dir, "index.faiss"))

    chunks_path = os.path.join(partial_dir, "chunks.jsonl")
    with open(chunks_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.model_dump(), ensure_ascii=True))
            handle.write("\n")

    manifest = Manifest(
        kb_version=kb_version,
        source_dir=source_dir,
        build_time=datetime.utcnow().isoformat() + "Z",
        embedding_model=embed_model,
        llm_provider_default=provider,
        faiss_metric="cosine",
        doc_count=0,
        chunk_count=len(records),
        failed_files=[item.get("chunk_id") or item.get("path") or "" for item in failed_items if item],
    )
    with open(os.path.join(partial_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest.model_dump(), handle, ensure_ascii=False, indent=2)


def _activate_partial_link(out_dir: str, partial_dir: str) -> None:
    current_path = os.path.join(out_dir, "current_partial")
    tmp_link = os.path.join(out_dir, "current_partial_tmp")
    relative_target = os.path.relpath(partial_dir, out_dir)
    if os.path.islink(tmp_link) or os.path.exists(tmp_link):
        if os.path.isdir(tmp_link) and not os.path.islink(tmp_link):
            shutil.rmtree(tmp_link)
        else:
            os.unlink(tmp_link)
    os.symlink(relative_target, tmp_link)
    os.replace(tmp_link, current_path)


def _split_table_rows(rows: List[List[str]], max_len: int) -> List[List[List[str]]]:
    if not rows or len(rows) <= 1 or max_len <= 0:
        return [rows]
    header = rows[0]
    body = rows[1:]
    chunks: List[List[List[str]]] = []
    current: List[List[str]] = []
    current_len = 0
    for row in body:
        row_text = table_to_linearized_text([header, row])
        row_len = len(row_text)
        if current and current_len + row_len > max_len:
            chunks.append([header] + current)
            current = []
            current_len = 0
        current.append(row)
        current_len += row_len
    if current:
        chunks.append([header] + current)
    if not chunks:
        chunks.append(rows)
    return chunks


def _embed_documents_with_retry(embeddings, texts: List[str], max_retries: int = 3) -> List[List[float]]:
    delay = 0.5
    last_exc: Optional[BaseException] = None
    for attempt in range(max_retries + 1):
        try:
            vectors = embeddings.embed_documents(texts)
            if len(vectors) != len(texts):
                raise RuntimeError(
                    f"Embedding batch returned mismatched vector count: expected {len(texts)}, got {len(vectors)}"
                )
            for index, vector in enumerate(vectors):
                vector_array = np.asarray(vector, dtype="float32")
                if vector_array.ndim != 1 or vector_array.size == 0:
                    raise RuntimeError(f"Embedding returned invalid vector at index {index}")
                if not np.all(np.isfinite(vector_array)):
                    raise RuntimeError(f"Embedding returned NaN/Inf vector at index {index}")
            return vectors
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Embedding failed after retries: {last_exc}") from last_exc


def _embed_batch_with_fallback(
    embeddings,
    batch_records: List[ChunkRecord],
) -> Tuple[List[ChunkRecord], List[List[float]], List[Dict[str, str]], List[str]]:
    """Embed one batch; on failure fallback to per-chunk with aggressive repair retry."""
    batch_texts = [record.text_for_embedding for record in batch_records]
    try:
        batch_vectors = _embed_documents_with_retry(embeddings, batch_texts)
        if len(batch_vectors) != len(batch_records):
            raise RuntimeError("Embedding batch returned mismatched vector count.")
        return batch_records, batch_vectors, [], []
    except Exception as exc:  # noqa: BLE001
        warnings: List[str] = [f"[WARN] embedding batch failed; fallback to per-chunk: {exc}"]
        kept_records: List[ChunkRecord] = []
        vectors: List[List[float]] = []
        failed: List[Dict[str, str]] = []
        for record in batch_records:
            try:
                vector = _embed_documents_with_retry(embeddings, [record.text_for_embedding])[0]
            except Exception as inner_exc:  # noqa: BLE001
                repaired_text = sanitize_embedding_text_aggressive(record.text_for_embedding)
                if repaired_text and repaired_text != record.text_for_embedding:
                    try:
                        vector = _embed_documents_with_retry(embeddings, [repaired_text])[0]
                        # Persist repaired text to keep embedding/query consistency.
                        record.text_for_embedding = repaired_text
                    except Exception as final_exc:  # noqa: BLE001
                        failed.append(
                            {
                                "chunk_id": record.chunk_id,
                                "file_path": record.file_path,
                                "reason": str(final_exc),
                            }
                        )
                        warnings.append(
                            f"[WARN] embedding failed; skipped chunk: {record.file_path}#{record.chunk_index}"
                        )
                        continue
                else:
                    failed.append(
                        {
                            "chunk_id": record.chunk_id,
                            "file_path": record.file_path,
                            "reason": str(inner_exc),
                        }
                    )
                    warnings.append(
                        f"[WARN] embedding failed; skipped chunk: {record.file_path}#{record.chunk_index}"
                    )
                    continue
            kept_records.append(record)
            vectors.append(vector)
        return kept_records, vectors, failed, warnings


def _collect_chunks(
    file_path: str,
    doc_hash: str,
    blocks,
    max_len: int,
    overlap: int,
) -> List[Dict[str, object]]:
    chunks: List[Dict[str, object]] = []
    repeated_short = _find_repeated_short_paragraphs(blocks)
    chunk_index = 0
    for block in blocks:
        if block.block_type == "paragraph":
            text = normalize_text(block.text)
            if not text:
                continue
            if text in repeated_short:
                continue
            items = split_list_items(text)
            for item in items:
                pieces = split_text(item, max_len=max_len, overlap=overlap)
                for piece in pieces:
                    raw_embedding_text = _attach_title_prefix(block.title_path, piece)
                    if is_low_signal_text(raw_embedding_text):
                        continue
                    embedding_text = sanitize_embedding_text(raw_embedding_text)
                    if not embedding_text:
                        continue
                    chunks.append(
                        {
                            "chunk_id": _build_chunk_id(file_path, doc_hash, chunk_index, "paragraph"),
                            "chunk_type": "paragraph",
                            "chunk_index": chunk_index,
                            "file_path": file_path,
                            "title_path": block.title_path,
                            "text_for_embedding": embedding_text,
                            "excerpt_markdown": piece,
                        }
                    )
                    chunk_index += 1
        elif block.block_type == "table":
            rows = getattr(block, "table_rows", None)
            if rows:
                table_chunks = _split_table_rows(rows, max_len=max_len)
                for table_rows in table_chunks:
                    table_markdown = table_to_markdown(table_rows)
                    table_text = table_to_linearized_text(table_rows)
                    if not table_markdown and not table_text:
                        continue
                    raw_embedding_text = _attach_title_prefix(block.title_path, table_text or table_markdown)
                    if is_low_signal_text(raw_embedding_text):
                        continue
                    embedding_text = sanitize_embedding_text(raw_embedding_text)
                    if not embedding_text:
                        continue
                    chunks.append(
                        {
                            "chunk_id": _build_chunk_id(file_path, doc_hash, chunk_index, "table"),
                            "chunk_type": "table",
                            "chunk_index": chunk_index,
                            "file_path": file_path,
                            "title_path": block.title_path,
                            "text_for_embedding": embedding_text,
                            "excerpt_markdown": table_markdown or table_text,
                        }
                    )
                    chunk_index += 1
                continue
            table_markdown = block.table_markdown or ""
            table_text = block.table_linearized_text or ""
            if not table_markdown and not table_text:
                continue
            raw_embedding_text = _attach_title_prefix(block.title_path, table_text or table_markdown)
            if is_low_signal_text(raw_embedding_text):
                continue
            embedding_text = sanitize_embedding_text(raw_embedding_text)
            if not embedding_text:
                continue
            chunks.append(
                {
                    "chunk_id": _build_chunk_id(file_path, doc_hash, chunk_index, "table"),
                    "chunk_type": "table",
                    "chunk_index": chunk_index,
                    "file_path": file_path,
                    "title_path": block.title_path,
                    "text_for_embedding": embedding_text,
                    "excerpt_markdown": table_markdown or table_text,
                }
            )
            chunk_index += 1
    return chunks

def build_kb(
    source_dir: str,
    out_dir: str,
    provider: str,
    embed_model: str,
    base_url: Optional[str],
    api_key: Optional[str],
    max_len: int = 800,
    overlap: int = 100,
    batch_size: int = 32,
    show_markdown: bool = False,
) -> Manifest:
    total_steps = 8
    start_time = time.perf_counter()
    stop_resource_monitor: Callable[[], None] = _start_resource_monitor("kb-build")
    _log_step(1, total_steps, "Scanning source documents", f"source_dir={source_dir}")
    included, skipped = scan_documents(source_dir)
    suspicious_count = sum(1 for item in skipped if item["reason"] in ("empty_file", "stat_failed"))
    total_count = len(included) + len(skipped)
    print(
        "Scan summary: "
        f"total={total_count}, included={len(included)}, skipped={len(skipped)}, suspicious={suspicious_count}"
    )
    _log_step(2, total_steps, "Confirming rebuild")
    if sys.stdin.isatty():
        answer = input("Proceed with rebuild? (y/n): ").strip().lower()
        if answer not in ("y", "yes"):
            raise UserAbort("KB rebuild aborted by user.")
    _log_step(3, total_steps, "Preparing output directories", f"out_dir={out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    versions_dir = os.path.join(out_dir, "versions")
    os.makedirs(versions_dir, exist_ok=True)

    kb_version = datetime.now().strftime("%Y%m%d-%H%M%S")
    version_dir = os.path.join(versions_dir, kb_version)
    os.makedirs(version_dir, exist_ok=True)

    failed_files: List[Dict[str, str]] = []
    degraded_files: List[Dict[str, str]] = []
    records: List[ChunkRecord] = []
    temp_dir = tempfile.mkdtemp(prefix="kb_docx_")

    try:
        _log_step(4, total_steps, "Parsing documents into chunks", f"documents={len(included)}")
        progress = tqdm(included, desc="Parsing documents")
        for path in progress:
            progress.set_postfix_str(safe_relpath(path, source_dir))
            try:
                doc_hash = sha1_file(path)
                ext = os.path.splitext(path)[1].lower()
                blocks = None
                if ext == ".doc":
                    converted, reason = convert_doc_to_docx(path, temp_dir)
                    if converted:
                        if show_markdown:
                            markdown, blocks = parse_docx_with_markdown(converted)
                            tqdm.write(f"[MARKDOWN] {safe_relpath(path, source_dir)}")
                            tqdm.write(markdown or "(empty)")
                        else:
                            blocks = parse_docx(converted)
                    else:
                        text, text_reason = _extract_doc_text_with_antiword(path)
                        if text:
                            degrade_reason = reason or "antiword_fallback"
                            blocks = blocks_from_text(text)
                            degraded_files.append(
                                {
                                    "path": path,
                                    "reason": text_reason or degrade_reason,
                                }
                            )
                            msg = safe_relpath(path, source_dir)
                            if text_reason or degrade_reason:
                                msg = f"{msg} ({text_reason or degrade_reason})"
                            tqdm.write(f"[WARN] degraded parse: {msg}")
                        else:
                            failed_files.append({"path": path, "reason": reason or "doc_convert_failed"})
                            msg = safe_relpath(path, source_dir)
                            if reason:
                                msg = f"{msg} ({reason})"
                            tqdm.write(f"[WARN] convert failed: {msg}")
                            continue
                else:
                    if show_markdown:
                        markdown, blocks = parse_docx_with_markdown(path)
                        tqdm.write(f"[MARKDOWN] {safe_relpath(path, source_dir)}")
                        tqdm.write(markdown or "(empty)")
                    else:
                        blocks = parse_docx(path)
                if not blocks:
                    failed_files.append({"path": path, "reason": "parse_empty"})
                    tqdm.write(f"[WARN] parse empty: {safe_relpath(path, source_dir)}")
                    continue
                chunks = _collect_chunks(
                    file_path=safe_relpath(path, source_dir),
                    doc_hash=doc_hash,
                    blocks=blocks,
                    max_len=max_len,
                    overlap=overlap,
                )
                if show_markdown:
                    for chunk in chunks:
                        title_path = chunk.get("title_path") or []
                        title_label = " > ".join([part for part in title_path if part])
                        excerpt = str(chunk.get("excerpt_markdown") or "")
                        excerpt = _shorten(excerpt.replace("\n", "\\n"))
                        tqdm.write(
                            "[CHUNK] "
                            f"{chunk['chunk_index']} "
                            f"type={chunk['chunk_type']} "
                            f"len={len(str(chunk.get('text_for_embedding') or ''))} "
                            f"title={title_label or '-'} "
                            f"text={excerpt}"
                        )
                for chunk in chunks:
                    records.append(
                        ChunkRecord(
                            vector_id=-1,
                            chunk_id=chunk["chunk_id"],
                            file_path=chunk["file_path"] if "file_path" in chunk else safe_relpath(path, source_dir),
                            title_path=chunk["title_path"],
                            chunk_type=chunk["chunk_type"],
                            chunk_index=chunk["chunk_index"],
                            doc_hash=doc_hash,
                            text_for_embedding=chunk["text_for_embedding"],
                            excerpt_markdown=chunk["excerpt_markdown"],
                        )
                    )
            except Exception:
                failed_files.append({"path": path, "reason": "parse_error"})
                tqdm.write(f"[WARN] parse failed: {safe_relpath(path, source_dir)}")

        if not records:
            raise RuntimeError("No chunks generated; check source directory and parsers.")

        resume_enabled = _env_flag("RAG_EMBED_RESUME", default=True)
        checkpoint_every = max(1, int(os.getenv("RAG_CHECKPOINT_EVERY_BATCHES", "20")))
        partial_every = max(0, int(os.getenv("RAG_PARTIAL_KB_EVERY_BATCHES", "50")))
        checkpoint_dir = os.path.join(out_dir, ".kb_checkpoint")
        checkpoint_signature = _checkpoint_signature(
            {
                "source_dir": source_dir,
                "provider": provider,
                "embed_model": embed_model,
                "max_len": max_len,
                "overlap": overlap,
                "batch_size": batch_size,
            }
        )
        checkpoint_embedded_path = os.path.join(checkpoint_dir, "embedded.jsonl")
        checkpoint_failed_path = os.path.join(checkpoint_dir, "failed.jsonl")

        resumed_map: Dict[str, Tuple[ChunkRecord, List[float]]] = {}
        resumed_failed: List[Dict[str, str]] = []
        resumed_loaded = 0
        if resume_enabled:
            resumed_map, resumed_failed, resumed_loaded = _load_embedding_checkpoint(
                checkpoint_dir,
                checkpoint_signature,
            )
        vectors: List[List[float]] = []
        kept_records: List[ChunkRecord] = []
        pending_records: List[ChunkRecord] = []
        for record in records:
            resumed = resumed_map.get(record.chunk_id)
            if resumed:
                resumed_record, resumed_vector = resumed
                record.text_for_embedding = resumed_record.text_for_embedding
                kept_records.append(record)
                vectors.append(resumed_vector)
            else:
                pending_records.append(record)

        embedding_failed: List[Dict[str, str]] = list(resumed_failed)
        if resumed_loaded > 0:
            tqdm.write(
                f"[RESUME] loaded {resumed_loaded} embedded chunk(s) from checkpoint; pending={len(pending_records)}"
            )
        elif resume_enabled:
            _write_checkpoint_state(
                checkpoint_dir,
                checkpoint_signature,
                {
                    "kb_version": kb_version,
                    "phase": "embedding",
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "total_chunks": len(records),
                    "embedded_chunks": 0,
                    "failed_chunks": len(embedding_failed),
                },
            )

        use_go_embedder = _env_flag("RAG_USE_GO_EMBEDDER", default=True)
        go_bin = _find_go_embedder() if use_go_embedder else None
        go_embed_concurrency = max(1, int(os.getenv("RAG_GO_EMBED_CONCURRENCY", "8")))
        if go_bin:
            _log_step(5, total_steps, "Initializing embedding model",
                      f"provider={provider}, model={embed_model}, backend=go-concurrent")
            embeddings = GoEmbedder(
                binary=go_bin,
                provider=provider,
                model=embed_model,
                base_url=base_url,
                api_key=api_key,
                concurrency=go_embed_concurrency,
            )
        else:
            if use_go_embedder:
                tqdm.write("[WARN] RAG_USE_GO_EMBEDDER=1 but go_embedder binary not found; fallback to python backend")
            _log_step(5, total_steps, "Initializing embedding model",
                      f"provider={provider}, model={embed_model}, backend=python")
            embeddings = build_embeddings(provider, embed_model, base_url=base_url, api_key=api_key)
        _log_step(6, total_steps, "Embedding chunks", f"chunks={len(records)}, batch_size={batch_size}")
        backend_name = "go-concurrent" if isinstance(embeddings, GoEmbedder) else "python"
        metrics = EmbedMetrics(backend=backend_name, requested_chunks=len(records), batch_size=batch_size)
        metrics_every = max(1, int(os.getenv("RAG_EMBED_METRICS_EVERY", "20")))
        with tqdm(total=len(records), desc="Embedding chunks") as progress:
            if resumed_loaded > 0:
                progress.update(resumed_loaded)

            def _after_batch(
                batch_kept: List[ChunkRecord],
                batch_vectors: List[List[float]],
                batch_failed: List[Dict[str, str]],
            ) -> None:
                nonlocal vectors, kept_records, embedding_failed
                next_batch_count = metrics.batch_count + 1
                kept_records.extend(batch_kept)
                vectors.extend(batch_vectors)
                embedding_failed.extend(batch_failed)
                if not resume_enabled:
                    return

                embed_rows = [
                    {"chunk_id": rec.chunk_id, "record": rec.model_dump(), "vector": vec}
                    for rec, vec in zip(batch_kept, batch_vectors)
                ]
                _append_checkpoint_rows(checkpoint_embedded_path, embed_rows)
                failed_rows = [
                    {
                        "chunk_id": str(item.get("chunk_id") or ""),
                        "file_path": str(item.get("file_path") or ""),
                        "reason": str(item.get("reason") or ""),
                    }
                    for item in batch_failed
                ]
                _append_checkpoint_rows(checkpoint_failed_path, failed_rows)
                if next_batch_count % checkpoint_every == 0:
                    _write_checkpoint_state(
                        checkpoint_dir,
                        checkpoint_signature,
                        {
                            "kb_version": kb_version,
                            "phase": "embedding",
                            "created_at": datetime.utcnow().isoformat() + "Z",
                            "updated_at": datetime.utcnow().isoformat() + "Z",
                            "total_chunks": len(records),
                            "embedded_chunks": len(kept_records),
                            "failed_chunks": len(embedding_failed),
                        },
                    )

                if partial_every > 0 and next_batch_count % partial_every == 0 and kept_records:
                    partial_dir = os.path.join(version_dir, "partial")
                    _write_partial_snapshot(
                        partial_dir=partial_dir,
                        records=kept_records,
                        vectors=vectors,
                        kb_version=kb_version,
                        source_dir=source_dir,
                        embed_model=embed_model,
                        provider=provider,
                        failed_items=embedding_failed,
                    )
                    _activate_partial_link(out_dir, partial_dir)

            if isinstance(embeddings, GoEmbedder):
                pipeline_workers = max(
                    1,
                    int(os.getenv("RAG_EMBED_PIPELINE_WORKERS", os.getenv("EMBED_PIPELINE_WORKERS", "8"))),
                )
                max_inflight = max(
                    1,
                    int(
                        os.getenv(
                            "RAG_EMBED_PIPELINE_INFLIGHT",
                            os.getenv("EMBED_PIPELINE_INFLIGHT", str(pipeline_workers * 2)),
                        )
                    ),
                )
                batch_iter = iter(iter_batches(pending_records, batch_size))
                in_flight = {}

                with ThreadPoolExecutor(max_workers=pipeline_workers) as executor:
                    def _submit_next() -> bool:
                        try:
                            next_batch = next(batch_iter)
                        except StopIteration:
                            return False
                        future = executor.submit(_embed_batch_with_fallback, embeddings, next_batch)
                        in_flight[future] = (len(next_batch), time.perf_counter())
                        return True

                    while len(in_flight) < max_inflight and _submit_next():
                        pass

                    while in_flight:
                        done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                        for future in done:
                            input_size, batch_start = in_flight.pop(future)
                            elapsed = time.perf_counter() - batch_start
                            batch_kept, batch_vectors, batch_failed, warns = future.result()
                            for msg in warns:
                                tqdm.write(msg)
                            _after_batch(batch_kept, batch_vectors, batch_failed)
                            metrics.batch_count += 1
                            metrics.total_batch_seconds += elapsed
                            metrics.kept_chunks += len(batch_kept)
                            metrics.failed_chunks += len(batch_failed)
                            if batch_failed:
                                metrics.failed_batches += 1
                            if metrics.batch_count % metrics_every == 0:
                                tqdm.write(
                                    "[EMBED_METRIC] "
                                    f"backend={backend_name} batch={metrics.batch_count} "
                                    f"elapsed_ms={elapsed * 1000:.1f} "
                                    f"kept={len(batch_kept)} failed={len(batch_failed)}"
                                )
                            progress.update(input_size)

                        while len(in_flight) < max_inflight and _submit_next():
                            pass
            else:
                for batch_records in iter_batches(pending_records, batch_size):
                    batch_start = time.perf_counter()
                    batch_kept, batch_vectors, batch_failed, warns = _embed_batch_with_fallback(
                        embeddings,
                        batch_records,
                    )
                    elapsed = time.perf_counter() - batch_start
                    for msg in warns:
                        tqdm.write(msg)
                    _after_batch(batch_kept, batch_vectors, batch_failed)
                    metrics.batch_count += 1
                    metrics.total_batch_seconds += elapsed
                    metrics.kept_chunks += len(batch_kept)
                    metrics.failed_chunks += len(batch_failed)
                    if batch_failed:
                        metrics.failed_batches += 1
                    if metrics.batch_count % metrics_every == 0:
                        tqdm.write(
                            "[EMBED_METRIC] "
                            f"backend={backend_name} batch={metrics.batch_count} "
                            f"elapsed_ms={elapsed * 1000:.1f} "
                            f"kept={len(batch_kept)} failed={len(batch_failed)}"
                        )
                    progress.update(len(batch_records))

        if resume_enabled:
            _write_checkpoint_state(
                checkpoint_dir,
                checkpoint_signature,
                {
                    "kb_version": kb_version,
                    "phase": "embedding_finished",
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "total_chunks": len(records),
                    "embedded_chunks": len(kept_records),
                    "failed_chunks": len(embedding_failed),
                },
            )

        tqdm.write(f"[EMBED_SUMMARY] {json.dumps(metrics.to_dict(), ensure_ascii=True)}")

        records = kept_records
        if embedding_failed:
            tqdm.write(f"[WARN] embedding failures: {len(embedding_failed)} chunk(s) skipped.")

        if not vectors:
            raise RuntimeError("Embedding returned no vectors.")

        _log_step(7, total_steps, "Building FAISS index", f"vectors={len(vectors)}")
        vector_array = np.array(vectors, dtype="float32")
        faiss.normalize_L2(vector_array)
        dim = vector_array.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vector_array)

        for idx, record in enumerate(records):
            record.vector_id = idx

        _log_step(8, total_steps, "Writing KB artifacts and activating version", f"kb_version={kb_version}")
        index_path = os.path.join(version_dir, "index.faiss")
        faiss.write_index(index, index_path)

        jsonl_path = os.path.join(version_dir, "chunks.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.model_dump(), ensure_ascii=True))
                handle.write("\n")

        manifest = Manifest(
            kb_version=kb_version,
            source_dir=source_dir,
            build_time=datetime.utcnow().isoformat() + "Z",
            embedding_model=embed_model,
            llm_provider_default=provider,
            faiss_metric="cosine",
            doc_count=len(included),
            chunk_count=len(records),
            failed_files=[item["path"] for item in failed_files],
        )
        manifest_path = os.path.join(version_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest.model_dump(), handle, ensure_ascii=False, indent=2)

        build_log = {
            "kb_version": kb_version,
            "source_dir": source_dir,
            "included_files": included,
            "skipped_files": skipped,
            "failed_files": failed_files,
            "degraded_files": degraded_files,
            "embedding_failed_chunks": embedding_failed,
            "embedding_metrics": metrics.to_dict(),
            "resume_enabled": resume_enabled,
            "checkpoint_every_batches": checkpoint_every,
            "partial_snapshot_every_batches": partial_every,
            "resumed_chunks": resumed_loaded,
        }
        build_log_path = os.path.join(version_dir, "build_log.json")
        with open(build_log_path, "w", encoding="utf-8") as handle:
            json.dump(build_log, handle, ensure_ascii=False, indent=2)

        _activate_version(out_dir, version_dir)
        if resume_enabled and os.path.exists(checkpoint_dir):
            shutil.rmtree(checkpoint_dir, ignore_errors=True)
        print("Activation completed.")
        print("版本激活完成。")
        elapsed = time.perf_counter() - start_time
        success_count = max(len(included) - len(failed_files), 0)
        print(
            "Build summary: "
            f"success={success_count}, failed={len(failed_files)}, skipped={len(skipped)}"
        )
        print(f"Build summary: duration={elapsed:.1f}s, output_dir={version_dir}")
        print(f"Build summary: kb_version={kb_version}")
        return manifest
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if "embeddings" in dir() and isinstance(embeddings, GoEmbedder):  # type: ignore[possibly-undefined]
            embeddings.close()  # type: ignore[possibly-undefined]
        stop_resource_monitor()


def _activate_version(out_dir: str, version_dir: str) -> None:
    current_path = os.path.join(out_dir, "current")
    tmp_link = os.path.join(out_dir, "current_tmp")
    relative_target = os.path.relpath(version_dir, out_dir)
    if os.path.islink(tmp_link) or os.path.exists(tmp_link):
        if os.path.isdir(tmp_link) and not os.path.islink(tmp_link):
            shutil.rmtree(tmp_link)
        else:
            os.unlink(tmp_link)
    try:
        os.symlink(relative_target, tmp_link)
        os.replace(tmp_link, current_path)
    except OSError:
        if os.path.exists(tmp_link):
            os.unlink(tmp_link)
        if os.path.exists(current_path):
            shutil.rmtree(current_path)
        shutil.copytree(version_dir, current_path)
