from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from core.config import settings
from core.logging import get_logger
from models.schemas.api import ReportArchiveRequest

router = APIRouter(tags=["reports"])
REPORTS_DIR = settings.REPORTS_DIR
logger = get_logger(__name__)

# Cache with 5-minute TTL
_LIST_REPORTS_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes
_DAY_DIR_RE = re.compile(r"^\d{8}$")
_REPORT_SUFFIXES = {".pdf", ".docx"}
_SOURCE_PREVIEW_SUFFIXES = {".doc", ".docx", ".pdf", ".md", ".txt"}
_GO_PROXY_HEALTH_CACHE: Dict[str, Any] = {
    "checked_at": 0.0,
    "healthy": False,
    "detail": "not_checked",
}
_GO_PROXY_HEALTH_TTL = 10


class ReportListCache:
    """Cache for report listings with TTL expiration."""

    @staticmethod
    def _cache_key(date: Optional[str]) -> str:
        return f"reports:{date or 'all'}"

    @staticmethod
    def get(date: Optional[str], state_token: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached report list if valid."""
        key = ReportListCache._cache_key(date)
        if key in _LIST_REPORTS_CACHE:
            entry = _LIST_REPORTS_CACHE[key]
            if (
                time.time() - entry["timestamp"] < _CACHE_TTL
                and entry.get("state_token") == state_token
            ):
                return entry["data"]
        return None

    @staticmethod
    def set(date: Optional[str], data: List[Dict[str, Any]], state_token: str) -> None:
        """Cache report list with current timestamp."""
        key = ReportListCache._cache_key(date)
        _LIST_REPORTS_CACHE[key] = {
            "data": data,
            "timestamp": time.time(),
            "state_token": state_token,
        }


def _reports_state_token(date: str | None = None) -> str:
    root = REPORTS_DIR / date if date else REPORTS_DIR
    if not root.exists() or not root.is_dir():
        return "missing"

    try:
        if date:
            return f"{root.stat().st_mtime_ns}:{sum(1 for _ in root.iterdir())}"

        latest_day_mtime_ns = 0
        day_count = 0
        for day_dir in root.iterdir():
            if not day_dir.is_dir() or day_dir.name.startswith("."):
                continue
            if not _DAY_DIR_RE.match(day_dir.name):
                continue
            day_count += 1
            latest_day_mtime_ns = max(latest_day_mtime_ns, day_dir.stat().st_mtime_ns)
        return f"{day_count}:{latest_day_mtime_ns}"
    except Exception:
        return "error"


def _proxy_enabled() -> bool:
    return settings.ENABLE_GO_REPORT_PROXY


def _go_base_url() -> str:
    return settings.GO_REPORT_SERVICE_URL.rstrip("/")


def _go_health_url() -> str:
    path = settings.GO_REPORT_HEALTH_PATH.strip() or "/healthz"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_go_base_url()}{path}"


def _proxy_fail_open_enabled() -> bool:
    return settings.GO_REPORT_PROXY_FAIL_OPEN


def _probe_go_proxy() -> tuple[bool, str]:
    now = time.time()
    if now - float(_GO_PROXY_HEALTH_CACHE.get("checked_at", 0.0)) <= _GO_PROXY_HEALTH_TTL:
        return bool(_GO_PROXY_HEALTH_CACHE.get("healthy", False)), str(_GO_PROXY_HEALTH_CACHE.get("detail", "unknown"))

    url = _go_health_url()
    req = urllib_request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(req, timeout=2) as resp:
            healthy = resp.getcode() < 400
            detail = f"http_{resp.getcode()}"
    except Exception as exc:
        healthy = False
        detail = str(exc)

    _GO_PROXY_HEALTH_CACHE["checked_at"] = now
    _GO_PROXY_HEALTH_CACHE["healthy"] = healthy
    _GO_PROXY_HEALTH_CACHE["detail"] = detail
    return healthy, detail


def _should_use_proxy() -> bool:
    if not _proxy_enabled():
        return False
    healthy, detail = _probe_go_proxy()
    if healthy:
        return True
    if _proxy_fail_open_enabled():
        logger.warning("[reports->go] proxy unhealthy, fallback to local implementation detail=%s", detail)
        return False
    raise HTTPException(status_code=502, detail=f"go_report_service_unavailable: {detail}")


def _proxy_call(
    method: str,
    path: str,
    *,
    query: Dict[str, Any] | None = None,
    payload: Dict[str, Any] | None = None,
) -> tuple[int, Dict[str, str], bytes]:
    query = query or {}
    query = {key: value for key, value in query.items() if value is not None}

    url = f"{_go_base_url()}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    body: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib_request.Request(url=url, data=body, method=method, headers=headers)
    logger.info("[reports->go] proxy request %s %s", method, url)

    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            resp_headers = dict(resp.headers.items())
            marker = resp_headers.get("X-Report-Service", "")
            logger.info(
                "[reports->go] proxy response status=%s service=%s",
                status,
                marker or "unknown",
            )
            return status, resp_headers, resp.read()
    except urllib_error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        resp_headers = dict(exc.headers.items()) if exc.headers else {}
        marker = resp_headers.get("X-Report-Service", "")
        logger.warning(
            "[reports->go] proxy http error status=%s service=%s",
            exc.code,
            marker or "unknown",
        )
        return exc.code, resp_headers, body
    except urllib_error.URLError as exc:
        logger.exception("[reports->go] proxy connection failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"go_report_service_unavailable: {exc}") from exc


def _extract_proxy_error_detail(body: bytes, default: str = "proxy_request_failed") -> str:
    if not body:
        return default
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        return default
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str):
            return detail
    return default


def _proxy_json(method: str, path: str, *, query: Dict[str, Any] | None = None, payload: Dict[str, Any] | None = None):
    status, _, body = _proxy_call(method, path, query=query, payload=payload)
    if status >= 400:
        detail = _extract_proxy_error_detail(body)
        raise HTTPException(status_code=status, detail=detail)
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"invalid_proxy_json: {exc}") from exc


def _proxy_file(method: str, path: str, *, query: Dict[str, Any] | None = None) -> Response:
    status, headers, body = _proxy_call(method, path, query=query)
    if status >= 400:
        detail = _extract_proxy_error_detail(body)
        raise HTTPException(status_code=status, detail=detail)

    passthrough_headers: Dict[str, str] = {}
    for key in ("Content-Disposition", "Cache-Control", "Content-Length"):
        value = headers.get(key)
        if value:
            passthrough_headers[key] = value

    media_type = headers.get("Content-Type", "application/octet-stream")
    return Response(content=body, status_code=status, media_type=media_type, headers=passthrough_headers)


def _list_reports(date: str | None = None):
    state_token = _reports_state_token(date)

    # Check cache first (5 minute TTL)
    cached = ReportListCache.get(date, state_token)
    if cached is not None:
        return cached

    reports = []
    root = REPORTS_DIR
    if date:
        root = REPORTS_DIR / date
        if not root.exists() or not root.is_dir():
            return []
        if root.name.startswith("."):
            return []

    for day_dir in sorted(root.iterdir() if root.is_dir() else [], reverse=True):
        if date and day_dir != root:
            continue
        if not day_dir.is_dir():
            continue
        if day_dir.name.startswith("."):
            continue
        if not _DAY_DIR_RE.match(day_dir.name):
            continue
        day = day_dir.name
        for item in day_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in _REPORT_SUFFIXES:
                continue
            stat_result = item.stat()
            reports.append(
                {
                    "date": day,
                    "name": item.name,
                    "size_bytes": stat_result.st_size,
                    "url": f"/reports/{day}/{item.name}",
                    "updated_at": stat_result.st_mtime,
                }
            )

    reports.sort(key=lambda report: report["updated_at"], reverse=True)

    # Cache the result
    ReportListCache.set(date, reports, state_token)
    return reports


def _reports_trash_dir() -> Path:
    trash_dir = REPORTS_DIR / ".trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    return trash_dir


def _resolve_report_path(date: str, filename: str) -> Path:
    candidate = (REPORTS_DIR / date / filename).resolve()
    if not candidate.is_relative_to(REPORTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="invalid_report_path")
    return candidate


def _resolve_trash_path(date: str, filename: str) -> Path:
    trash_dir = _reports_trash_dir()
    candidate = (trash_dir / date / filename).resolve()
    if not candidate.is_relative_to(trash_dir.resolve()):
        raise HTTPException(status_code=400, detail="invalid_report_path")
    return candidate


def _extract_source_doc_relative_path(source: str) -> str:
    raw = str(source or "").strip()
    if not raw or raw == "-":
        return ""
    normalized = raw
    for prefix in ("来源：", "来源:", "source:", "Source:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    match = re.search(r"([A-Za-z0-9_./\\-]+\.(?:docx?|DOCX?))", normalized)
    if match:
        normalized = match.group(1)
    normalized = normalized.replace("\\", "/").strip().lstrip("./")
    return normalized


def _extract_source_title(source: str) -> str:
    raw = str(source or "").strip()
    if not raw or raw == "-":
        return ""
    normalized = raw
    for prefix in ("来源：", "来源:", "source:", "Source:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    return normalized.strip()


def _canonical_source_name(value: str) -> str:
    normalized = _extract_source_title(value)
    normalized = re.sub(r"\.(docx?|pdf|md|txt)$", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.lower()
    normalized = re.sub(r"[\s\-_./\\:：()（）\[\]【】<>《》]+", "", normalized)
    return normalized


def _iter_source_candidates_by_title(source: str, allowed_roots: List[Path]) -> List[Path]:
    canonical = _canonical_source_name(source)
    if not canonical:
        return []

    preferred_roots: List[Path] = []
    seen_roots: set[Path] = set()
    for root in allowed_roots:
        if root in seen_roots or not root.exists() or not root.is_dir():
            continue
        seen_roots.add(root)
        preferred_roots.append(root)

    subdirs = ("docs", "config", "rag/dataset", "rag/kb")
    for root in list(preferred_roots):
        for subdir in subdirs:
            candidate = root / subdir
            if candidate.exists() and candidate.is_dir() and candidate not in seen_roots:
                seen_roots.add(candidate)
                preferred_roots.append(candidate)

    matches: List[Path] = []
    checked: set[Path] = set()
    for root in preferred_roots:
        try:
            iterator = root.rglob("*")
        except Exception:
            continue
        for candidate in iterator:
            if not candidate.is_file():
                continue
            suffix = candidate.suffix.lower()
            if suffix not in _SOURCE_PREVIEW_SUFFIXES:
                continue
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if resolved in checked:
                continue
            checked.add(resolved)
            stem_key = _canonical_source_name(candidate.stem)
            name_key = _canonical_source_name(candidate.name)
            if canonical in {stem_key, name_key}:
                matches.append(resolved)
    return matches


def _kb_source_preview_entries(source: str) -> List[Dict[str, Any]]:
    canonical = _canonical_source_name(source)
    if not canonical:
        return []

    project_root = Path(__file__).resolve().parents[1]
    kb_candidates = [
        project_root / "rag" / "kb" / "knowledge_base.jsonl",
        project_root / "rag" / "kb" / "current_partial" / "chunks.jsonl",
    ]

    entries: List[Dict[str, Any]] = []
    for kb_path in kb_candidates:
        if not kb_path.exists() or not kb_path.is_file():
            continue
        try:
            with kb_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(item, dict):
                        continue
                    source_value = str(item.get("source") or item.get("file_path") or "").strip()
                    if _canonical_source_name(source_value) != canonical:
                        continue
                    entries.append(
                        {
                            "id": str(item.get("id") or item.get("chunk_id") or "").strip(),
                            "title": str(item.get("title") or "").strip(),
                            "content": str(
                                item.get("content")
                                or item.get("excerpt_markdown")
                                or item.get("text_for_embedding")
                                or ""
                            ).strip(),
                            "tags": item.get("tags") or [],
                            "source": source_value,
                        }
                    )
        except Exception:
            logger.exception("failed to load knowledge-base preview entries from %s", kb_path)
    return entries


def _build_kb_source_preview_text(source: str, entries: List[Dict[str, Any]]) -> str:
    lines = [
        f"来源标题: {_extract_source_title(source) or source}",
        "说明: 未找到原始附件文件，以下内容为知识库中同来源条目的汇总预览。",
        "",
    ]
    for index, entry in enumerate(entries, start=1):
        title = str(entry.get("title") or "未命名条目")
        entry_id = str(entry.get("id") or "-")
        tags = entry.get("tags") or []
        if isinstance(tags, list):
            tag_text = ", ".join(str(tag).strip() for tag in tags if str(tag).strip())
        else:
            tag_text = str(tags).strip()
        content = str(entry.get("content") or "").strip()
        lines.append(f"[{index}] {title}")
        lines.append(f"条目ID: {entry_id}")
        if tag_text:
            lines.append(f"标签: {tag_text}")
        if content:
            lines.append(content)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _source_preview_response(source: str, entries: List[Dict[str, Any]], inline: bool) -> Response:
    preview = _build_kb_source_preview_text(source, entries)
    disposition = "inline" if inline else "attachment"
    title = _extract_source_title(source) or "source-preview"
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", title).strip("_") or "source-preview"
    quoted_name = quote(f"{safe_name}.txt")
    headers = {
        "Content-Disposition": f"{disposition}; filename=\"source-preview.txt\"; filename*=UTF-8''{quoted_name}",
    }
    return Response(content=preview, media_type="text/plain; charset=utf-8", headers=headers)


def _resolve_source_doc_path(source: str) -> Path:
    normalized = _extract_source_doc_relative_path(source)
    if not normalized:
        raise HTTPException(status_code=404, detail="source_file_not_found")

    project_root = Path(__file__).resolve().parents[1]
    rag_dataset_root = project_root / "rag" / "dataset"
    allowed_roots: List[Path] = [project_root.resolve(), rag_dataset_root.resolve()]

    env_source_root = os.getenv("RAG_SOURCE_ROOT", "").strip()
    if env_source_root:
        try:
            allowed_roots.append(Path(env_source_root).resolve())
        except Exception:
            pass

    env_kb_source_dir = os.getenv("KB_SOURCE_DIR", "").strip()
    if env_kb_source_dir:
        try:
            allowed_roots.append(Path(env_kb_source_dir).resolve())
        except Exception:
            pass

    path = Path(normalized)
    candidates: List[Path] = []
    if normalized.startswith("tcm/"):
        candidates.append(rag_dataset_root / normalized)

    if path.is_absolute():
        candidates.append(path)
    else:
        for root in allowed_roots:
            candidates.append(root / path)

    checked: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved in checked:
            continue
        checked.add(resolved)
        if resolved.suffix.lower() not in {".doc", ".docx"}:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        if any(resolved.is_relative_to(root) for root in allowed_roots):
            return resolved

    for resolved in _iter_source_candidates_by_title(source, allowed_roots):
        if any(resolved.is_relative_to(root) for root in allowed_roots):
            return resolved

    raise HTTPException(status_code=404, detail="source_file_not_found")


def _rewrite_report_urls(items):
    """Rewrite Go-internal /v1/reports/... URLs to public /reports/... URLs."""
    if not isinstance(items, list):
        return items
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            item["url"] = item["url"].replace("/v1/reports/", "/reports/", 1)
    return items


@router.get("/reports")
def list_reports(date: str | None = None):
    if _should_use_proxy():
        return _rewrite_report_urls(_proxy_json("GET", "/v1/reports", query={"date": date}))
    return _list_reports(date=date)


@router.get("/reports/.trash")
def list_trash_reports():
    if _should_use_proxy():
        return _rewrite_report_urls(_proxy_json("GET", "/v1/reports/trash"))

    trash_dir = _reports_trash_dir()
    reports = []

    for day_dir in sorted(trash_dir.iterdir() if trash_dir.is_dir() else [], reverse=True):
        if not day_dir.is_dir():
            continue
        if not _DAY_DIR_RE.match(day_dir.name):
            continue
        day = day_dir.name
        for item in day_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in _REPORT_SUFFIXES:
                continue
            reports.append(
                {
                    "date": day,
                    "name": item.name,
                    "size_bytes": item.stat().st_size,
                    "url": f"/reports/.trash/{day}/{item.name}",
                    "updated_at": item.stat().st_mtime,
                }
            )

    reports.sort(key=lambda report: report["updated_at"], reverse=True)
    return reports


@router.get("/reports/.trash/{date}/{filename}")
def download_trash_report(date: str, filename: str):
    if _should_use_proxy():
        encoded_name = quote(filename)
        return _proxy_file("GET", f"/v1/reports/trash/{date}/{encoded_name}", query={"inline": "true"})

    trash_path = _resolve_trash_path(date, filename)
    if not trash_path.exists() or not trash_path.is_file():
        raise HTTPException(status_code=404, detail="report_not_found")

    ascii_name = "report" + trash_path.suffix
    quoted_name = quote(trash_path.name)
    content_disposition = (
        f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted_name}"
    )
    headers = {"Content-Disposition": content_disposition}
    return FileResponse(trash_path, headers=headers)


@router.post("/reports/archive")
def archive_report(request: ReportArchiveRequest):
    if _should_use_proxy():
        return _proxy_json("POST", "/v1/reports/archive", payload=request.model_dump())

    report_path = _resolve_report_path(request.date, request.filename)
    trash_path = _resolve_trash_path(request.date, request.filename)

    if request.archived:
        if not report_path.exists() or not report_path.is_file():
            raise HTTPException(status_code=404, detail="report_not_found")
        trash_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(report_path), str(trash_path))
        _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(None), None)
        _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(request.date), None)
        return {"status": "archived", "date": request.date, "filename": request.filename}

    if not trash_path.exists() or not trash_path.is_file():
        raise HTTPException(status_code=404, detail="report_not_archived")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        raise HTTPException(status_code=409, detail="report_already_exists")
    shutil.move(str(trash_path), str(report_path))
    _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(None), None)
    _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(request.date), None)
    return {"status": "restored", "date": request.date, "filename": request.filename}


@router.get("/reports/source-file")
def download_source_file(source: str, inline: bool = True):
    try:
        candidate = _resolve_source_doc_path(source)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        preview_entries = _kb_source_preview_entries(source)
        if not preview_entries:
            raise
        return _source_preview_response(source, preview_entries, inline=inline)

    disposition = "inline" if inline else "attachment"
    ascii_name = "source" + candidate.suffix
    quoted_name = quote(candidate.name)
    content_disposition = (
        f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted_name}"
    )
    headers = {"Content-Disposition": content_disposition}
    return FileResponse(candidate, headers=headers)


@router.get("/reports/{date}/{filename}")
def download_report(date: str, filename: str, inline: bool = False):
    if _should_use_proxy():
        encoded_name = quote(filename)
        return _proxy_file("GET", f"/v1/reports/{date}/{encoded_name}", query={"inline": str(inline).lower()})

    candidate = (REPORTS_DIR / date / filename).resolve()
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="report_not_found")
    if not candidate.is_relative_to(REPORTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="invalid_report_path")
    disposition = "inline" if inline else "attachment"
    ascii_name = "report" + candidate.suffix
    quoted_name = quote(candidate.name)
    content_disposition = (
        f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted_name}"
    )
    headers = {"Content-Disposition": content_disposition}
    return FileResponse(candidate, headers=headers)


@router.get("/reports/preview")
def preview_report(date: str, filename: str):
    if _should_use_proxy():
        encoded_name = quote(filename)
        return _proxy_file("GET", f"/v1/reports/{date}/{encoded_name}", query={"inline": "true"})

    try:
        candidate = (REPORTS_DIR / date / filename).resolve()
        logger.info("preview_report: candidate=%s exists=%s", candidate, candidate.exists())
        
        if not candidate.exists() or not candidate.is_file():
            logger.warning("Report file not found: %s", candidate)
            raise HTTPException(status_code=404, detail="report_not_found")
        
        if not candidate.is_relative_to(REPORTS_DIR.resolve()):
            logger.warning("Invalid report path (path traversal attempt?): %s", candidate)
            raise HTTPException(status_code=400, detail="invalid_report_path")
        
        ascii_name = "report" + candidate.suffix
        quoted_name = quote(candidate.name, safe='')
        content_disposition = (
            f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted_name}"
        )
        headers = {"Content-Disposition": content_disposition}
        
        logger.info("Returning FileResponse for: %s", candidate)
        return FileResponse(candidate, headers=headers, media_type="application/octet-stream")
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error previewing report: date=%s filename=%s", date, filename)
        raise HTTPException(status_code=500, detail="preview_error")


@router.get("/reports/proxy-health")
def reports_proxy_health():
    enabled = _proxy_enabled()
    if not enabled:
        return {
            "enabled": False,
            "using_proxy": False,
            "healthy": False,
            "fail_open": _proxy_fail_open_enabled(),
            "detail": "proxy_disabled",
        }

    healthy, detail = _probe_go_proxy()
    return {
        "enabled": True,
        "using_proxy": healthy,
        "healthy": healthy,
        "fail_open": _proxy_fail_open_enabled(),
        "detail": detail,
        "base_url": _go_base_url(),
        "health_url": _go_health_url(),
    }
