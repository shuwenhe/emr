import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .data_platform import get_emr_by_record_id, save_emr, save_report
from .config import DATA_DIR, EMR_DIR
from .report_docx import generate_docx_report
from .report_template import generate_template_report


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
    try:
        return _load_json(path)
    except Exception:
        return None


def _report_path(record_id: str) -> Path:
    return _record_dir(record_id) / "report.json"


def generate_emr(record_id: str, force: bool = False) -> Dict[str, Any]:
    from .analysis import analyze_record
    record_dir = _record_dir(record_id)
    if not record_dir.exists():
        raise FileNotFoundError("record_not_found")

    # 幂等性检查：如果EMR已存在且未强制重新生成，则直接返回
    if not force:
        existing = get_emr_by_record_id(record_id)
        if existing:
            logging.info("EMR already exists for record %s (emr_id=%s), returning existing", record_id, existing.get("emr_id"))
            return existing

    analyze_result = analyze_record(record_id)
    report = analyze_result.get("report") or {}
    plan = analyze_result.get("plan") or {}

    metadata_path = record_dir / "metadata.json"
    metadata = _safe_load(metadata_path) or {}

    patient = metadata.get("patient") or {}
    clinical = metadata.get("clinical") or {}

    existing = get_emr_by_record_id(record_id)
    emr_id = existing.get("emr_id") if existing else f"EMR-{uuid.uuid4()}"
    created_at = datetime.now().isoformat(timespec="seconds")

    emr = {
        "emr_id": emr_id,
        "record_id": record_id,
        "created_at": created_at,
        "archived": False,
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
        json.dump(emr, handle, ensure_ascii=False, indent=2, default=str)

    save_emr(emr)

    if report:
        try:
            # FastReport disabled, use DOCX directly
            report_path = generate_docx_report(report, emr)
            logging.info("DOCX report generated: %s", report_path)
        except Exception as exc:
            logging.exception("DOCX report generation failed for emr %s: %s", emr_id, exc)

    return emr


def upsert_emr_from_analysis(
    record_id: str,
    report: Dict[str, Any],
    plan: Dict[str, Any],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    existing = get_emr_by_record_id(record_id)
    emr_id = existing.get("emr_id") if existing else f"EMR-{uuid.uuid4()}"
    created_at = existing.get("created_at") if existing else datetime.now().isoformat(timespec="seconds")

    patient = metadata.get("patient") or {}
    clinical = metadata.get("clinical") or {}

    emr = {
        "emr_id": emr_id,
        "record_id": record_id,
        "created_at": created_at,
        "archived": existing.get("archived") if existing else False,
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
        json.dump(emr, handle, ensure_ascii=False, indent=2, default=str)

    save_emr(emr)
    return emr


def _resolve_data_image_path(path_value: Any) -> Optional[Path]:
    raw = str(path_value or "").strip()
    if not raw:
        return None

    candidate = Path(raw)
    if candidate.exists() and candidate.is_file():
        return candidate

    normalized = raw.lstrip("/")
    if normalized.startswith("data/"):
        normalized = normalized[5:]
    candidate = DATA_DIR / normalized
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _refresh_roi_labeled_image(emr: Dict[str, Any]) -> bool:
    report = emr.get("report")
    if not isinstance(report, dict):
        return False

    analysis = report.get("analysis")
    if not isinstance(analysis, dict):
        return False
    roi_analysis = analysis.get("roi_analysis")
    if not isinstance(roi_analysis, dict) or not isinstance(roi_analysis.get("roi_list"), list):
        return False

    record_id = str(emr.get("record_id") or report.get("record_id") or "").strip()
    if not record_id:
        return False

    marked = _resolve_data_image_path(report.get("thermal_marked_image"))
    if marked is None:
        thermal_images = report.get("thermal_images")
        if isinstance(thermal_images, list):
            for item in thermal_images:
                marked = _resolve_data_image_path(item)
                if marked is not None:
                    break
    if marked is None:
        return False

    try:
        from .analysis import _generate_roi_labeled_image
    except Exception:
        return False

    out_path = DATA_DIR / record_id / "thermal_roi_labeled.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generated = _generate_roi_labeled_image(str(marked), roi_analysis, out_path)
    if not generated:
        return False

    relative = str(Path(generated).relative_to(DATA_DIR))
    report["thermal_roi_labeled_image"] = relative

    thermal_images = report.get("thermal_images")
    if isinstance(thermal_images, list) and relative not in thermal_images:
        thermal_images.append(relative)
    elif not isinstance(thermal_images, list):
        report["thermal_images"] = [relative]

    emr["report"] = report
    return True


def get_emr(emr_id: str) -> Dict[str, Any]:
    path = _emr_path(emr_id)
    if not path.exists():
        raise EmrNotFoundError("emr_not_found")

    emr = _load_json(path)
    updated = _refresh_roi_labeled_image(emr)
    if updated:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(emr, handle, ensure_ascii=False, indent=2)

        record_id = emr.get("record_id")
        report = emr.get("report")
        if isinstance(record_id, str) and record_id and isinstance(report, dict):
            report_path = _report_path(record_id)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
            try:
                save_report(record_id, report)
            except Exception:
                pass

        try:
            save_emr(emr)
        except Exception:
            pass

    return emr


def update_emr(emr_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    emr = get_emr(emr_id)
    record_id = emr.get("record_id")
    report_updated = False

    report = emr.get("report") or {}
    if not report and record_id:
        report = _safe_load(_report_path(record_id)) or {}

    for key in ("diagnosis", "doctor_opinion", "treatment_plan"):
        if key in updates and updates[key] is not None:
            emr[key] = updates[key]
            if key in {"diagnosis", "doctor_opinion"}:
                report[key] = updates[key]
                report_updated = True

    if "clinical" in updates and isinstance(updates["clinical"], dict):
        emr.setdefault("clinical", {})
        for c_key, c_value in updates["clinical"].items():
            if c_value is not None:
                emr["clinical"][c_key] = c_value

    if "report" in updates and isinstance(updates["report"], dict):
        emr["report"] = updates["report"]
        report = updates["report"]
        report_updated = True

    if report_updated and record_id:
        emr["report"] = report
        report_path = _report_path(record_id)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        try:
            save_report(record_id, report)
        except Exception:
            emr.setdefault("warnings", []).append("report_db_save_failed")
        try:
            # FastReport disabled, use DOCX directly
            generate_docx_report(report, emr)
        except Exception:
            emr.setdefault("warnings", []).append("report_docx_generate_failed")

    with open(_emr_path(emr_id), "w", encoding="utf-8") as handle:
        json.dump(emr, handle, ensure_ascii=False, indent=2)

    save_emr(emr)
    return emr


def archive_emr(emr_id: str, archived: bool = True) -> Dict[str, Any]:
    emr = get_emr(emr_id)
    emr["archived"] = archived

    with open(_emr_path(emr_id), "w", encoding="utf-8") as handle:
        json.dump(emr, handle, ensure_ascii=False, indent=2)

    save_emr(emr)
    return emr


def list_emrs(patient_id: Optional[str] = None, include_archived: bool = False) -> List[Dict[str, Any]]:
    emrs: List[Dict[str, Any]] = []
    for item in EMR_DIR.glob("EMR-*.json"):
        data = _safe_load(item)
        if not data:
            continue
        if patient_id:
            emr_patient_id = (data.get("patient") or {}).get("patient_id")
            if emr_patient_id != patient_id:
                continue
        if not include_archived and data.get("archived"):
            continue
        emrs.append(data)

    emrs.sort(key=lambda item: item.get("created_at") or "")
    return emrs
