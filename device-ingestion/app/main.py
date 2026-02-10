import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .config import ALLOWED_EXTENSIONS, MAX_FILE_MB
from .models import IngestMetadata
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
        parsed = IngestMetadata.parse_obj(metadata_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_metadata") from exc

    file_bytes = await file.read()
    _validate_size(file_bytes)

    qc_issues = run_qc(parsed)
    result = save_payload(file.filename, file_bytes, parsed.dict())

    return {
        **result,
        "qc_issues": qc_issues,
    }
