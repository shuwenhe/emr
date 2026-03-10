from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from src.backend.models.schemas.api import AnalyzeRequest, DeviceIngestRequest, DispatchRequest, IngestMetadata
from src.backend.services.analysis import AnalysisService
from src.backend.services.emr import EMRService
from src.backend.services.ingestion import IngestionService
from src.backend.services.treatment import TreatmentService

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".dat"}
MAX_FILE_MB = 100
analysis_service = AnalysisService()
ingestion_service = IngestionService()
emr_service = EMRService()
treatment_service = TreatmentService()


def _validate_file(file: UploadFile) -> None:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported_file_type")


def _validate_size(file_bytes: bytes) -> None:
    max_bytes = MAX_FILE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="file_too_large")


def _generate_report_after_ingest(record_id: str) -> None:
    try:
        logger.info("Starting background report generation for record %s", record_id)
        result = emr_service.create_emr(record_id)
        if result:
            logger.info("Report generation completed for record %s, emr_id=%s", record_id, result.get("emr_id"))
    except Exception as exc:
        logger.exception("Report generation failed for record %s: %s", record_id, exc)


@router.post("/ingest")
async def ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form(...),
):
    _validate_file(file)

    try:
        metadata_json = json.loads(metadata)
        parsed = IngestMetadata.model_validate(metadata_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_metadata") from exc

    file_bytes = await file.read()
    _validate_size(file_bytes)

    tmp_file = Path("/tmp") / file.filename
    tmp_file.write_bytes(file_bytes)
    record_id = ingestion_service.ingest_data(tmp_file, parsed.model_dump(), validate=True)
    result = {"record_id": record_id, "storage_path": None, "matrix_csv_path": None}
    background_tasks.add_task(_generate_report_after_ingest, result["record_id"])

    return {
        **result,
        "qc_issues": [],  # No QC issues if validation passed
        "report_generation": "scheduled",
    }


@router.post("/device/ingest")
def ingest_from_device(request: DeviceIngestRequest):
    if request.capture_path:
        try:
            return ingestion_service.ingest_capture_dir(request.capture_path, move_to_processed=request.move_to_processed)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else "capture_path_not_found")) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="capture_ingest_failed") from exc

    return ingestion_service.ingest_pending_captures(move_to_processed=request.move_to_processed)


@router.post("/analyze")
def analyze(request: AnalyzeRequest):
    try:
        return analysis_service.analyze_record(request.record_id)
    except FileNotFoundError as exc:
        detail = exc.args[0] if exc.args else "record_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/dispatch")
def dispatch(request: DispatchRequest):
    try:
        return treatment_service.dispatch_to_device({"record_id": request.record_id}, device_id="default")
    except FileNotFoundError as exc:
        detail = exc.args[0] if exc.args else "dispatch_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc
