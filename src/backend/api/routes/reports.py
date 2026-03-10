from __future__ import annotations

import shutil
import time
from pathlib import Path
from urllib.parse import quote
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.backend.core.config import settings
from src.backend.models.schemas.api import ReportArchiveRequest

router = APIRouter(tags=["reports"])
REPORTS_DIR = settings.REPORTS_DIR

# Cache with 5-minute TTL
_LIST_REPORTS_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes


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
        day = day_dir.name
        for item in day_dir.iterdir():
            if not item.is_file():
                continue
            # Merge two stat() calls into one
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

    reports.sort(key=lambda r: r["updated_at"], reverse=True)
    
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
    return _list_reports(date=date)


@router.get("/reports/.trash")
def list_trash_reports():
    trash_dir = _reports_trash_dir()
    reports = []

    for day_dir in sorted(trash_dir.iterdir() if trash_dir.is_dir() else [], reverse=True):
        if not day_dir.is_dir():
            continue
        day = day_dir.name
        for item in day_dir.iterdir():
            if not item.is_file():
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

    reports.sort(key=lambda r: r["updated_at"], reverse=True)
    return reports


@router.get("/reports/.trash/{date}/{filename}")
def download_trash_report(date: str, filename: str):
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
    report_path = _resolve_report_path(request.date, request.filename)
    trash_path = _resolve_trash_path(request.date, request.filename)

    if request.archived:
        if not report_path.exists() or not report_path.is_file():
            raise HTTPException(status_code=404, detail="report_not_found")
        trash_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(report_path), str(trash_path))
        # Invalidate relevant caches
        _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(None), None)
        _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(request.date), None)
        return {"status": "archived", "date": request.date, "filename": request.filename}

    if not trash_path.exists() or not trash_path.is_file():
        raise HTTPException(status_code=404, detail="report_not_archived")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        raise HTTPException(status_code=409, detail="report_already_exists")
    shutil.move(str(trash_path), str(report_path))
    # Invalidate relevant caches
    _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(None), None)
    _LIST_REPORTS_CACHE.pop(ReportListCache._cache_key(request.date), None)
    return {"status": "restored", "date": request.date, "filename": request.filename}


@router.get("/reports/{date}/{filename}")
def download_report(date: str, filename: str, inline: bool = False):
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
