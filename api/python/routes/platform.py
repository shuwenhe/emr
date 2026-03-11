from __future__ import annotations

import json
import time
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi import APIRouter

from core.config import settings
from models.schemas.api import HistoryImportRequest
from services.platform import PlatformService

router = APIRouter(tags=["platform"])
platform_service = PlatformService()

_GO_PLATFORM_HEALTH_CACHE = {
    "checked_at": 0.0,
    "healthy": False,
    "detail": "not_checked",
}
_GO_PLATFORM_HEALTH_TTL = 10


def _platform_proxy_enabled() -> bool:
    return settings.ENABLE_GO_PLATFORM_PROXY


def _platform_base_url() -> str:
    return settings.GO_PLATFORM_SERVICE_URL.rstrip("/")


def _platform_health_url() -> str:
    path = settings.GO_PLATFORM_HEALTH_PATH.strip() or "/healthz"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_platform_base_url()}{path}"


def _platform_fail_open_enabled() -> bool:
    return settings.GO_PLATFORM_PROXY_FAIL_OPEN


def _probe_platform_proxy() -> tuple[bool, str]:
    now = time.time()
    if now - float(_GO_PLATFORM_HEALTH_CACHE.get("checked_at", 0.0)) <= _GO_PLATFORM_HEALTH_TTL:
        return bool(_GO_PLATFORM_HEALTH_CACHE.get("healthy", False)), str(_GO_PLATFORM_HEALTH_CACHE.get("detail", "unknown"))

    url = _platform_health_url()
    req = urllib_request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(req, timeout=2) as resp:
            healthy = resp.getcode() < 400
            detail = f"http_{resp.getcode()}"
    except Exception as exc:
        healthy = False
        detail = str(exc)

    _GO_PLATFORM_HEALTH_CACHE["checked_at"] = now
    _GO_PLATFORM_HEALTH_CACHE["healthy"] = healthy
    _GO_PLATFORM_HEALTH_CACHE["detail"] = detail
    return healthy, detail


def _should_use_platform_proxy() -> bool:
    if not _platform_proxy_enabled():
        return False
    healthy, detail = _probe_platform_proxy()
    if healthy:
        return True
    if _platform_fail_open_enabled():
        return False
    raise HTTPException(status_code=502, detail=f"go_platform_service_unavailable: {detail}")


def _proxy_platform_summary():
    url = f"{_platform_base_url()}/v1/platform/summary"
    req = urllib_request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            if not body:
                return {}
            return json.loads(body.decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = "proxy_request_failed"
        try:
            payload = json.loads((exc.read() or b"{}").decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                detail = payload["detail"]
        except Exception:
            pass
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except Exception as exc:
        if _platform_fail_open_enabled():
            return platform_service.summary()
        raise HTTPException(status_code=502, detail=f"go_platform_service_unavailable: {exc}") from exc


def _proxy_platform_records(patient_id: str | None = None, limit: int = 50):
    params = {"limit": limit}
    if patient_id:
        params["patient_id"] = patient_id
    query = urlencode(params)
    url = f"{_platform_base_url()}/v1/platform/records"
    if query:
        url = f"{url}?{query}"

    req = urllib_request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            if not body:
                return []
            return json.loads(body.decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = "proxy_request_failed"
        try:
            payload = json.loads((exc.read() or b"{}").decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                detail = payload["detail"]
        except Exception:
            pass
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except Exception as exc:
        if _platform_fail_open_enabled():
            return platform_service.list_records(patient_id=patient_id, limit=limit)
        raise HTTPException(status_code=502, detail=f"go_platform_service_unavailable: {exc}") from exc


@router.post("/import/history")
def import_history(request: HistoryImportRequest):
    return platform_service.import_history(request.root_path, analyze=request.analyze)


@router.get("/platform/summary")
def platform_summary():
    if _should_use_platform_proxy():
        return _proxy_platform_summary()
    return platform_service.summary()


@router.get("/platform/records")
def platform_records(patient_id: str | None = None, limit: int = 50):
    if _should_use_platform_proxy():
        return _proxy_platform_records(patient_id=patient_id, limit=limit)
    return platform_service.list_records(patient_id=patient_id, limit=limit)


@router.get("/platform/emrs")
def platform_emrs(patient_id: str | None = None, limit: int = 50, include_archived: bool = False):
    return platform_service.list_platform_emrs(patient_id=patient_id, limit=limit, include_archived=include_archived)


@router.get("/platform/proxy-health")
def platform_proxy_health():
    enabled = _platform_proxy_enabled()
    if not enabled:
        return {
            "enabled": False,
            "using_proxy": False,
            "healthy": False,
            "fail_open": _platform_fail_open_enabled(),
            "detail": "proxy_disabled",
        }

    healthy, detail = _probe_platform_proxy()
    return {
        "enabled": True,
        "using_proxy": healthy,
        "healthy": healthy,
        "fail_open": _platform_fail_open_enabled(),
        "detail": detail,
        "base_url": _platform_base_url(),
        "health_url": _platform_health_url(),
    }
