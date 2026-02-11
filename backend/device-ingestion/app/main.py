import asyncio
import json
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_EXTENSIONS, MAX_FILE_MB, REPORTS_DIR
from .analysis import analyze_record
from .device_connector import (
    ingest_capture_dir,
    ingest_pending_captures,
    import_history_dir,
    move_capture_dir,
    poll_device_drop,
)
from .data_platform import init_db, list_emrs as list_platform_emrs, list_records, summary, upsert_patient, list_patients
from .dispatch import dispatch_record
from .emr import EmrNotFoundError, archive_emr, generate_emr, get_emr, list_emrs, update_emr
from .models import (
    AnalyzeRequest,
    DeviceIngestRequest,
    DispatchRequest,
    EmrGenerateRequest,
    EmrUpdateRequest,
    EmrArchiveRequest,
    HistoryImportRequest,
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


def _list_reports(date: str | None = None):
    reports = []
    root = REPORTS_DIR
    if date:
        root = REPORTS_DIR / date
        if not root.exists() or not root.is_dir():
            return []

    for day_dir in sorted(root.iterdir() if root.is_dir() else [], reverse=True):
        if date and day_dir != root:
            continue
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
                    "url": f"/reports/{day}/{item.name}",
                    "updated_at": item.stat().st_mtime,
                }
            )

    reports.sort(key=lambda r: r["updated_at"], reverse=True)
    return reports


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
def list_emr_endpoint(patient_id: str | None = None, include_archived: bool = False):
    return list_emrs(patient_id=patient_id, include_archived=include_archived)


@app.put("/emr/{emr_id}")
def update_emr_endpoint(emr_id: str, request: EmrUpdateRequest):
    try:
        return update_emr(emr_id, request.model_dump(exclude_none=True))
    except EmrNotFoundError as exc:
        detail = exc.args[0] if exc.args else "emr_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@app.post("/emr/{emr_id}/archive")
def archive_emr_endpoint(emr_id: str, request: EmrArchiveRequest):
    try:
        return archive_emr(emr_id, request.archived)
    except EmrNotFoundError as exc:
        detail = exc.args[0] if exc.args else "emr_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@app.post("/import/history")
def import_history(request: HistoryImportRequest):
    root_dir = Path(request.root_path)
    result = import_history_dir(root_dir)
    if request.analyze:
        analyzed = []
        for item in result["ingested"]:
            record_id = item.get("record_id")
            if record_id:
                analyzed.append(analyze_record(record_id))
        result["analyzed"] = analyzed
    return result


@app.get("/platform/summary")
def platform_summary():
    return summary()


@app.post("/patients")
async def register_patient(patient: dict):
    """Register a new patient"""
    import uuid
    from datetime import datetime
    
    # Generate patient_id if not provided
    if not patient.get("patient_id"):
        patient["patient_id"] = f"P{uuid.uuid4().hex[:12].upper()}"
    
    # Calculate age from birth_date if provided
    if patient.get("birth_date") and not patient.get("age"):
        birth_date = datetime.fromisoformat(patient["birth_date"].replace("Z", "+00:00"))
        patient["age"] = datetime.now().year - birth_date.year
    
    # Upsert patient to database
    patient_id = upsert_patient(patient)
    
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_registration_failed")
    
    return {"patient_id": patient_id, "message": "patient_registered_successfully"}


@app.get("/patients")
def get_patients(limit: int = 100):
    """Get all registered patients"""
    return list_patients(limit=limit)


@app.get("/platform/records")
def platform_records(patient_id: str | None = None, limit: int = 50):
    return list_records(patient_id=patient_id, limit=limit)


@app.get("/platform/emrs")
def platform_emrs(patient_id: str | None = None, limit: int = 50, include_archived: bool = False):
    return list_platform_emrs(patient_id=patient_id, limit=limit, include_archived=include_archived)


@app.get("/reports")
def list_reports(date: str | None = None):
    return _list_reports(date=date)


@app.get("/reports/{date}/{filename}")
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


@app.on_event("startup")
async def start_device_polling():
    global _device_stop_event
    init_db()
    _device_stop_event = asyncio.Event()
    asyncio.create_task(poll_device_drop(_device_stop_event))


@app.on_event("shutdown")
async def stop_device_polling():
    if _device_stop_event is not None:
        _device_stop_event.set()
