from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models.schemas.api import EmrArchiveRequest, EmrGenerateRequest, EmrUpdateRequest
from service.emr import EMRService
from service.platform import PlatformService

router = APIRouter(tags=["emr"])
emr_service = EMRService()
platform_service = PlatformService()


@router.post("/emr/generate")
def generate_emr_endpoint(request: EmrGenerateRequest):
    try:
        return emr_service.create_emr(request.record_id, force=bool(request.force))
    except FileNotFoundError as exc:
        detail = exc.args[0] if exc.args else "record_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.get("/emr/{emr_id}")
def get_emr_endpoint(emr_id: str):
    try:
        return emr_service.get_emr(emr_id)
    except Exception as exc:
        detail = exc.args[0] if exc.args else "emr_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.get("/emr")
def list_emr_endpoint(
    patient_id: str | None = None,
    record_id: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
):
    limit = min(limit, 1000)

    if record_id:
        return platform_service.list_platform_emrs(
            record_id=record_id,
            patient_id=patient_id,
            limit=1,
            include_archived=include_archived,
        )

    return platform_service.list_platform_emrs(
        patient_id=patient_id,
        limit=limit,
        include_archived=include_archived,
    )


@router.put("/emr/{emr_id}")
def update_emr_endpoint(emr_id: str, request: EmrUpdateRequest):
    try:
        return emr_service.update_emr(emr_id, request.model_dump(exclude_none=True))
    except Exception as exc:
        detail = exc.args[0] if exc.args else "emr_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/emr/{emr_id}/archive")
def archive_emr_endpoint(emr_id: str, request: EmrArchiveRequest):
    try:
        return emr_service.archive_emr(emr_id, request.archived)
    except Exception as exc:
        detail = exc.args[0] if exc.args else "emr_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc
