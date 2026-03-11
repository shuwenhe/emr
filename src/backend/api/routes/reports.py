from __future__ import annotations

import json
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

from src.backend.core.config import settings
from src.backend.core.logging import get_logger
from src.backend.models.schemas.api import ReportArchiveRequest

router = APIRouter(tags=["reports"])
REPORTS_DIR = settings.REPORTS_DIR
logger = get_logger(__name__)

# Cache with 5-minute TTL
_LIST_REPORTS_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes
_DAY_DIR_RE = re.compile(r"^\d{8}$")
_REPORT_SUFFIXES = {".pdf", ".docx"}


class ReportListCache:
    """Cache for report listings with TTL expiration."""

    @staticmethod
    def _cache_key(date: Optional[str]) -> str:
        return f"reports:{date or 'all'}"

    @staticmethod
    def get(date: Optional[str]) -> Optional[List[Dict[str, Any]]]:
        """Get cached report list if valid."""
        key = ReportListCache._cache_key(date)
        if key in _LIST_REPORTS_CACHE:
            entry = _LIST_REPORTS_CACHE[key]
            if time.time() - entry["timestamp"] < _CACHE_TTL:
                return entry["data"]
        return None

    @staticmethod
    def set(date: Optional[str], data: List[Dict[str, Any]]) -> None:
        """Cache report list with current timestamp."""
        key = ReportListCache._cache_key(date)
        _LIST_REPORTS_CACHE[key] = {
            "data": data,
            "timestamp": time.time(),
        }


def _proxy_enabled() -> bool:
    return settings.ENABLE_GO_REPORT_PROXY


def _go_base_url() -> str:
    return settings.GO_REPORT_SERVICE_URL.rstrip("/")


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
    # Check cache first (5 minute TTL)
    cached = ReportListCache.get(date)
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
    ReportListCache.set(date, reports)
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


@router.get("/reports")
def list_reports(date: str | None = None):
    if _proxy_enabled():
        return _proxy_json("GET", "/v1/reports", query={"date": date})
    return _list_reports(date=date)


@router.get("/reports/.trash")
def list_trash_reports():
    if _proxy_enabled():
        return _proxy_json("GET", "/v1/reports/trash")

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
    if _proxy_enabled():
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
    if _proxy_enabled():
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


@router.get("/reports/{date}/{filename}")
def download_report(date: str, filename: str, inline: bool = False):
    if _proxy_enabled():
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
    if _proxy_enabled():
        encoded_name = quote(filename)
        return _proxy_file("GET", f"/v1/reports/{date}/{encoded_name}", query={"inline": "true"})

    candidate = (REPORTS_DIR / date / filename).resolve()
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="report_not_found")
    if not candidate.is_relative_to(REPORTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="invalid_report_path")
    ascii_name = "report" + candidate.suffix
    quoted_name = quote(candidate.name)
    content_disposition = (
        f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted_name}"
    )
    headers = {"Content-Disposition": content_disposition}
    return FileResponse(candidate, headers=headers)
