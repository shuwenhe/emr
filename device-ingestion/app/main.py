import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .config import ALLOWED_EXTENSIONS, MAX_FILE_MB
from .analysis import analyze_record
from .dispatch import dispatch_record
from .models import AnalyzeRequest, DispatchRequest, IngestMetadata
from .qc import run_qc
from .storage import save_payload

app = FastAPI(title="Device Ingestion Service")


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
