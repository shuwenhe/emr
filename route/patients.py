from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from models.schemas.api import (
    PatientArchiveRequest,
    PatientDeleteRequest,
    PatientSoftDeleteRequest,
    PatientUpsertRequest,
)
from service.platform import PlatformService
from route.events import publish_patient_event

router = APIRouter(tags=["patients"])
platform_service = PlatformService()


@router.delete("/patients/{patient_id}")
def delete_patient_endpoint(patient_id: str):
    success = platform_service.delete_patient(patient_id)
    if not success:
        raise HTTPException(status_code=404, detail="patient_not_found")
    return {"message": "patient_soft_deleted", "patient_id": patient_id}


@router.post("/patients/{patient_id}/soft-delete")
def soft_delete_patient_endpoint(patient_id: str, request: PatientSoftDeleteRequest):
    if request.deleted:
        success = platform_service.delete_patient(patient_id)
        if not success:
            raise HTTPException(status_code=404, detail="patient_not_found")
        return {"message": "patient_soft_deleted", "patient_id": patient_id}

    restored = platform_service.restore_deleted_patient(patient_id)
    if not restored:
        raise HTTPException(status_code=404, detail="patient_not_found")
    return restored


@router.post("/patients/{patient_id}/restore")
def restore_patient_endpoint(patient_id: str):
    restored = platform_service.restore_deleted_patient(patient_id)
    if not restored:
        raise HTTPException(status_code=404, detail="patient_not_found")
    return restored


@router.post("/patients/batch-delete")
def batch_delete_patients_endpoint(request: PatientDeleteRequest):
    results = []
    for patient_id in request.patient_ids:
        success = platform_service.delete_patient(patient_id)
        results.append({"patient_id": patient_id, "deleted": success})
    return {"results": results}


@router.post("/patients")
async def register_patient(patient: PatientUpsertRequest):
    payload = patient.model_dump(exclude_none=True)

    if not payload.get("patient_id"):
        payload["patient_id"] = f"P{uuid.uuid4().hex[:12].upper()}"

    if payload.get("birth_date") and not payload.get("age"):
        birth_date = datetime.fromisoformat(payload["birth_date"].replace("Z", "+00:00"))
        payload["age"] = datetime.now().year - birth_date.year

    patient_id = platform_service.upsert_patient(payload)

    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_registration_failed")

    await publish_patient_event("patient_registered", patient_id)

    return {"patient_id": patient_id, "message": "patient_registered_successfully"}


@router.get("/patients")
async def get_patients(
    page: int = 1,
    limit: int = 20,
    include_archived: bool = False,
    include_deleted: bool = False,
):
    offset = (page - 1) * limit
    # Run blocking DB query in thread pool to keep event loop responsive
    return await asyncio.to_thread(
        platform_service.list_patients,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        include_deleted=include_deleted,
    )


@router.get("/patients/{patient_id}")
def get_patient_endpoint(patient_id: str):
    patient = platform_service.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="patient_not_found")
    return patient


@router.put("/patients/{patient_id}")
def update_patient_endpoint(patient_id: str, request: PatientUpsertRequest):
    payload = request.model_dump(exclude_none=True)
    updated = platform_service.update_patient(patient_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="patient_not_found")
    return updated


@router.post("/patients/{patient_id}/archive")
async def archive_patient_endpoint(patient_id: str, request: PatientArchiveRequest):
    # Run blocking DB work in a thread so async endpoints stay responsive.
    updated = await asyncio.to_thread(
        platform_service.archive_patient,
        patient_id,
        request.archived,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="patient_not_found")
    # Best-effort event publish: do not hold API response on slow SSE clients.
    try:
        await asyncio.wait_for(publish_patient_event("patient_archived", patient_id), timeout=0.5)
    except Exception:
        pass
    return updated
