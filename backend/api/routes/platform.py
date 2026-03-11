from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas.api import HistoryImportRequest
from backend.services.platform import PlatformService

router = APIRouter(tags=["platform"])
platform_service = PlatformService()


@router.post("/import/history")
def import_history(request: HistoryImportRequest):
    return platform_service.import_history(request.root_path, analyze=request.analyze)


@router.get("/platform/summary")
def platform_summary():
    return platform_service.summary()


@router.get("/platform/records")
def platform_records(patient_id: str | None = None, limit: int = 50):
    return platform_service.list_records(patient_id=patient_id, limit=limit)


@router.get("/platform/emrs")
def platform_emrs(patient_id: str | None = None, limit: int = 50, include_archived: bool = False):
    return platform_service.list_platform_emrs(patient_id=patient_id, limit=limit, include_archived=include_archived)
