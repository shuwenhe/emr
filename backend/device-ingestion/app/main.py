import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_EXTENSIONS, MAX_FILE_MB
from .analysis import analyze_record
from .device_connector import (
    ingest_capture_dir,
    ingest_pending_captures,
    move_capture_dir,
    poll_device_drop,
)
from .dispatch import dispatch_record
from .emr import EmrNotFoundError, generate_emr, get_emr, list_emrs
from .models import (
    AnalyzeRequest,
    DeviceIngestRequest,
    DispatchRequest,
    EmrGenerateRequest,
    IngestMetadata,
)
from .qc import run_qc
from .storage import save_payload

app = FastAPI(title="Device Ingestion Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
_device_stop_event: asyncio.Event | None = None


def _validate_file(file: UploadFile) -> None:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported_file_type")


def _validate_size(file_bytes: bytes) -> None:
    max_bytes = MAX_FILE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="file_too_large")


@app.post("/ingest")
async def ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    _validate_file(file)

    try:
        metadata_json = json.loads(metadata)
        parsed = IngestMetadata.model_validate(metadata_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_metadata") from exc

    file_bytes = await file.read()
    _validate_size(file_bytes)

    qc_issues = run_qc(parsed)
    result = save_payload(file.filename, file_bytes, parsed.model_dump())

    return {
        **result,
        "qc_issues": qc_issues,
    }


@app.post("/device/ingest")
def ingest_from_device(request: DeviceIngestRequest):
    if request.capture_path:
        capture_dir = Path(request.capture_path)
        if not capture_dir.exists() or not capture_dir.is_dir():
            raise HTTPException(status_code=404, detail="capture_path_not_found")
        try:
            result = ingest_capture_dir(capture_dir)
            if request.move_to_processed:
                move_capture_dir(capture_dir)
            return {
                "ingested": [result],
                "skipped": [],
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail="capture_ingest_failed") from exc

    return ingest_pending_captures(move_to_processed=request.move_to_processed)


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    try:
        return analyze_record(request.record_id)
    except FileNotFoundError as exc:
        detail = exc.args[0] if exc.args else "record_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@app.post("/dispatch")
def dispatch(request: DispatchRequest):
    try:
        return dispatch_record(request.record_id)
    except FileNotFoundError as exc:
        detail = exc.args[0] if exc.args else "dispatch_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@app.post("/emr/generate")
def generate_emr_endpoint(request: EmrGenerateRequest):
    try:
        return generate_emr(request.record_id)
    except FileNotFoundError as exc:
        detail = exc.args[0] if exc.args else "record_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@app.get("/emr/{emr_id}")
def get_emr_endpoint(emr_id: str):
    try:
        return get_emr(emr_id)
    except EmrNotFoundError as exc:
        detail = exc.args[0] if exc.args else "emr_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@app.get("/emr")
def list_emr_endpoint(patient_id: str | None = None):
    return list_emrs(patient_id=patient_id)


@app.on_event("startup")
async def start_device_polling():
    global _device_stop_event
    _device_stop_event = asyncio.Event()
    asyncio.create_task(poll_device_drop(_device_stop_event))


@app.on_event("shutdown")
async def stop_device_polling():
    if _device_stop_event is not None:
        _device_stop_event.set()
