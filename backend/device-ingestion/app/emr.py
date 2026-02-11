import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analysis import analyze_record
from .config import DATA_DIR, EMR_DIR


class EmrNotFoundError(FileNotFoundError):
    pass


def _record_dir(record_id: str) -> Path:
    return DATA_DIR / record_id


def _emr_path(emr_id: str) -> Path:
    return EMR_DIR / f"{emr_id}.json"


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return _load_json(path)


def generate_emr(record_id: str) -> Dict[str, Any]:
    record_dir = _record_dir(record_id)
    if not record_dir.exists():
        raise FileNotFoundError("record_not_found")

    analyze_result = analyze_record(record_id)
    report = analyze_result.get("report") or {}
    plan = analyze_result.get("plan") or {}

    metadata_path = record_dir / "metadata.json"
    metadata = _safe_load(metadata_path) or {}

    patient = metadata.get("patient") or {}
    clinical = metadata.get("clinical") or {}

    emr_id = f"EMR-{uuid.uuid4()}"
    created_at = datetime.now().isoformat(timespec="seconds")

    emr = {
        "emr_id": emr_id,
        "record_id": record_id,
        "created_at": created_at,
        "patient": {
            "patient_id": patient.get("patient_id"),
            "name": patient.get("name"),
            "gender": patient.get("gender"),
            "age": patient.get("age"),
            "body_part": patient.get("body_part"),
            "posture": patient.get("posture"),
        },
        "clinical": {
            "chief_complaint": clinical.get("chief_complaint"),
            "past_history": clinical.get("past_history") or [],
            "family_history": clinical.get("family_history") or [],
            "allergies": clinical.get("allergies") or [],
            "medications": clinical.get("medications") or [],
        },
        "diagnosis": report.get("diagnosis"),
        "doctor_opinion": report.get("doctor_opinion"),
        "thermal_images": report.get("thermal_images") or [],
        "report": report,
        "treatment_plan": plan,
    }

    with open(_emr_path(emr_id), "w", encoding="utf-8") as handle:
        json.dump(emr, handle, ensure_ascii=False, indent=2)

    return emr


def get_emr(emr_id: str) -> Dict[str, Any]:
    path = _emr_path(emr_id)
    if not path.exists():
        raise EmrNotFoundError("emr_not_found")
    return _load_json(path)


def list_emrs(patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
    emrs: List[Dict[str, Any]] = []
    for item in EMR_DIR.glob("EMR-*.json"):
        data = _safe_load(item)
        if not data:
            continue
        if patient_id:
            emr_patient_id = (data.get("patient") or {}).get("patient_id")
            if emr_patient_id != patient_id:
                continue
        emrs.append(data)

    emrs.sort(key=lambda item: item.get("created_at") or "")
    return emrs
