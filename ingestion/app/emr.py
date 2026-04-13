import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .data_platform import get_emr_by_record_id, save_emr, save_report
from .config import DATA_DIR, EMR_DIR
from reports.python import generate_docx_report, generate_pdf_report, generate_template_report
from reports.python.thermal_label_renderer import render_labeled_thermal_image


REPORT_PRIMARY_FORMAT = os.getenv("EMR_REPORT_PRIMARY_FORMAT", "pdf").strip().lower()
EMR_ENABLE_OPTIONAL_DOCX = os.getenv("EMR_ENABLE_OPTIONAL_DOCX", "1").strip().lower() in {"1", "true", "yes", "on"}
EMR_REPORT_PARALLEL_ENABLED = os.getenv("EMR_REPORT_PARALLEL_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
EMR_REPORT_PARALLEL_WORKERS = max(1, int(os.getenv("EMR_REPORT_PARALLEL_WORKERS", "8")))


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


def _persist_emr_and_report(emr: Dict[str, Any]) -> None:
    emr_id = str(emr.get("emr_id") or "").strip()
    if emr_id:
        with open(_emr_path(emr_id), "w", encoding="utf-8") as handle:
            json.dump(emr, handle, ensure_ascii=False, indent=2, default=str)

    save_emr(emr)

    record_id = str(emr.get("record_id") or "").strip()
    report = emr.get("report")
    if record_id and isinstance(report, dict):
        report_path = _report_path(record_id)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        save_report(record_id, report)


def _has_valid_report_file(emr: Dict[str, Any], field_name: str) -> bool:
    raw_path = str(emr.get(field_name) or "").strip()
    if not raw_path:
        report = emr.get("report")
        if isinstance(report, dict):
            raw_path = str(report.get(field_name) or "").strip()
    if not raw_path:
        return False

    report_file = Path(raw_path)
    return report_file.exists() and report_file.is_file()


def _generate_report_outputs(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    *,
    require_primary: bool = True,
) -> bool:
    generated_any = False
    primary_format = REPORT_PRIMARY_FORMAT if REPORT_PRIMARY_FORMAT in {"pdf", "docx"} else "pdf"
    generated_at = datetime.now()

    def _run_pdf() -> Optional[Path]:
        started_at = time.perf_counter()
        path = generate_pdf_report(report, emr, generated_at=generated_at)
        logging.info(
            "[EMR-TIMING] record_id=%s stage=generate_pdf_report elapsed=%.3fs success=%s",
            emr.get("record_id"),
            time.perf_counter() - started_at,
            bool(path),
        )
        return path

    def _run_docx() -> Optional[Path]:
        started_at = time.perf_counter()
        path = generate_docx_report(report, emr, generated_at=generated_at)
        logging.info(
            "[EMR-TIMING] record_id=%s stage=generate_docx_report elapsed=%.3fs success=%s",
            emr.get("record_id"),
            time.perf_counter() - started_at,
            bool(path),
        )
        return path

    if primary_format == "pdf":
        need_pdf = not _has_valid_report_file(emr, "pdf_report_path")
        need_docx = EMR_ENABLE_OPTIONAL_DOCX and not _has_valid_report_file(emr, "docx_report_path")

        # Generate PDF and DOCX in parallel when both are missing.
        if need_pdf and need_docx and EMR_REPORT_PARALLEL_ENABLED:
            try:
                with ThreadPoolExecutor(max_workers=min(2, EMR_REPORT_PARALLEL_WORKERS), thread_name_prefix="emr-report") as pool:
                    pdf_future = pool.submit(_run_pdf)
                    docx_future = pool.submit(_run_docx)

                    pdf_path = pdf_future.result()
                    docx_path = docx_future.result()

                if pdf_path:
                    emr["pdf_report_path"] = str(pdf_path)
                    report["pdf_report_path"] = str(pdf_path)
                    generated_any = True
                elif require_primary:
                    emr.setdefault("warnings", []).append("report_pdf_generate_failed")
                    return False

                if docx_path:
                    emr["docx_report_path"] = str(docx_path)
                    report["docx_report_path"] = str(docx_path)
                    generated_any = True
                else:
                    emr.setdefault("warnings", []).append("report_docx_generate_failed")
            except Exception as exc:
                logging.exception("Parallel report generation failed for emr %s: %s", emr.get("emr_id"), exc)
                emr.setdefault("warnings", []).append("report_pdf_generate_failed")
                emr.setdefault("warnings", []).append("report_docx_generate_failed")
                if require_primary:
                    return False
        else:
            if need_pdf:
                try:
                    pdf_path = _run_pdf()
                    if pdf_path:
                        emr["pdf_report_path"] = str(pdf_path)
                        report["pdf_report_path"] = str(pdf_path)
                        generated_any = True
                    elif require_primary:
                        emr.setdefault("warnings", []).append("report_pdf_generate_failed")
                        return False
                except Exception as exc:
                    logging.exception("PDF report generation failed for emr %s: %s", emr.get("emr_id"), exc)
                    emr.setdefault("warnings", []).append("report_pdf_generate_failed")
                    if require_primary:
                        return False

            if need_docx:
                try:
                    docx_path = _run_docx()
                    if docx_path:
                        emr["docx_report_path"] = str(docx_path)
                        report["docx_report_path"] = str(docx_path)
                        generated_any = True
                    else:
                        emr.setdefault("warnings", []).append("report_docx_generate_failed")
                except Exception as exc:
                    logging.exception("DOCX report generation failed for emr %s: %s", emr.get("emr_id"), exc)
                    emr.setdefault("warnings", []).append("report_docx_generate_failed")
    else:
        if not _has_valid_report_file(emr, "docx_report_path"):
            try:
                docx_path = _run_docx()
                if docx_path:
                    emr["docx_report_path"] = str(docx_path)
                    report["docx_report_path"] = str(docx_path)
                    generated_any = True
                elif require_primary:
                    emr.setdefault("warnings", []).append("report_docx_generate_failed")
                    return False
            except Exception as exc:
                logging.exception("DOCX report generation failed for emr %s: %s", emr.get("emr_id"), exc)
                emr.setdefault("warnings", []).append("report_docx_generate_failed")
                if require_primary:
                    return False

    emr["report"] = report
    return generated_any or _has_valid_report_file(emr, f"{primary_format}_report_path")


def _ensure_report_outputs(emr: Dict[str, Any]) -> bool:
    report = emr.get("report")
    if not isinstance(report, dict) or not report:
        return False
    return _generate_report_outputs(report, emr, require_primary=False)


def generate_emr(
    record_id: str,
    force: bool = False,
    *,
    enable_roi: bool = True,
    enable_llm: bool = False,
    ensure_report_outputs: bool = True,
) -> Dict[str, Any]:
    from .analysis import analyze_record
    record_dir = _record_dir(record_id)
    if not record_dir.exists():
        raise FileNotFoundError("record_not_found")

    # 幂等性检查：如果EMR已存在且未强制重新生成，则直接返回
    if not force:
        existing = get_emr_by_record_id(record_id)
        if existing:
            logging.info("EMR already exists for record %s (emr_id=%s), returning existing", record_id, existing.get("emr_id"))
            if ensure_report_outputs:
                try:
                    outputs_updated = _ensure_report_outputs(existing)
                    if outputs_updated:
                        _persist_emr_and_report(existing)
                        logging.info("Report outputs backfilled for existing EMR record=%s emr_id=%s", record_id, existing.get("emr_id"))
                except Exception as exc:
                    logging.warning("Report output backfill skipped for existing EMR record=%s error=%s", record_id, exc)
            return existing

    analysis_started_at = time.perf_counter()
    analyze_result = analyze_record(
        record_id,
        enable_roi=enable_roi,
        enable_llm=enable_llm,
    )
    logging.info(
        "[EMR-TIMING] record_id=%s stage=analyze_record elapsed=%.3fs enable_roi=%s enable_llm=%s",
        record_id,
        time.perf_counter() - analysis_started_at,
        enable_roi,
        enable_llm,
    )
    report = analyze_result.get("report") or {}
    plan = analyze_result.get("plan") or {}

    metadata_path = record_dir / "metadata.json"
    metadata = _safe_load(metadata_path) or {}

    patient = metadata.get("patient") or {}
    clinical = metadata.get("clinical") or {}

    existing = get_emr_by_record_id(record_id)
    emr_id = existing.get("emr_id") if existing else f"EMR-{uuid.uuid4()}"
    created_at = datetime.now().isoformat(timespec="seconds")

    # Extract temperature metrics and risk level from report.analysis
    analysis = report.get("analysis") if isinstance(report, dict) else {}
    temperature_metrics = analysis.get("temperature_metrics") if isinstance(analysis, dict) else None
    body_avg_temp_c = analysis.get("body_avg_temp_c") if isinstance(analysis, dict) else None
    risk_level = analysis.get("risk_level") if isinstance(analysis, dict) else "unknown"
    
    # Build temperature_metrics with both avg_c and body_avg_temp_c
    if temperature_metrics and isinstance(temperature_metrics, dict):
        full_metrics = dict(temperature_metrics)
        if body_avg_temp_c is not None:
            full_metrics["body_avg_temp_c"] = body_avg_temp_c
    else:
        full_metrics = {}

    emr = {
        "emr_id": emr_id,
        "record_id": record_id,
        "created_at": created_at,
        "archived": False,
        "risk_level": risk_level,
        "temperature_metrics": full_metrics if full_metrics else None,
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
        "thermal_roi_labeled_image": report.get("thermal_roi_labeled_image"),
        "thermal_marked_image": report.get("thermal_marked_image"),
        "report": report,
        "treatment_plan": plan,
    }

    _persist_emr_and_report(emr)

    if report and ensure_report_outputs:
        logging.info(
            "Attempting to generate primary report output for emr %s (report_id=%s, primary=%s, optional_docx=%s)",
            emr_id,
            report.get("report_id"),
            REPORT_PRIMARY_FORMAT,
            EMR_ENABLE_OPTIONAL_DOCX,
        )
        if _generate_report_outputs(report, emr, require_primary=True):
            _persist_emr_and_report(emr)
        else:
            logging.warning("Primary report generation failed for emr %s", emr_id)
    elif not report:
        logging.warning("Report is empty/None for emr %s, skipping report generation", emr_id)

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

    # Extract temperature metrics and risk level from report.analysis
    analysis = report.get("analysis") if isinstance(report, dict) else {}
    temperature_metrics = analysis.get("temperature_metrics") if isinstance(analysis, dict) else None
    body_avg_temp_c = analysis.get("body_avg_temp_c") if isinstance(analysis, dict) else None
    risk_level = analysis.get("risk_level") if isinstance(analysis, dict) else "unknown"
    
    # Build temperature_metrics with both avg_c and body_avg_temp_c
    if temperature_metrics and isinstance(temperature_metrics, dict):
        full_metrics = dict(temperature_metrics)
        if body_avg_temp_c is not None:
            full_metrics["body_avg_temp_c"] = body_avg_temp_c
    else:
        full_metrics = {}

    emr = {
        "emr_id": emr_id,
        "record_id": record_id,
        "created_at": created_at,
        "archived": existing.get("archived") if existing else False,
        "risk_level": risk_level,
        "temperature_metrics": full_metrics if full_metrics else None,
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
        "thermal_roi_labeled_image": report.get("thermal_roi_labeled_image"),
        "thermal_marked_image": report.get("thermal_marked_image"),
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


def _normalize_emr_fields(emr: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize metrics from report.analysis if not in emr root."""
    if not isinstance(emr, dict):
        return emr
    
    result = dict(emr)
    report = result.get("report")
    if isinstance(report, dict):
        analysis = report.get("analysis", {})
        if isinstance(analysis, dict):
            if "brief_summary" not in result and "brief_summary" in analysis:
                result["brief_summary"] = analysis["brief_summary"]
            if "risk_level" not in result and "risk_level" in analysis:
                result["risk_level"] = analysis["risk_level"]
    
    return result


def _prioritize_report_paths(emr: Dict[str, Any]) -> Dict[str, Any]:
    """Reorder EMR dict to prioritize pdf_report_path before docx_report_path.
    
    This ensures that when the frontend displays field results, PDFs are shown first.
    """
    if not isinstance(emr, dict):
        return emr
    
    # Build new dict with desired field order
    ordered = {}
    
    # Priority fields first
    priority_fields = ["emr_id", "record_id", "patient", "hospital", "pdf_report_path", "docx_report_path"]
    for field in priority_fields:
        if field in emr:
            ordered[field] = emr[field]
    
    # Then add remaining fields in original order
    for key, value in emr.items():
        if key not in ordered:
            ordered[key] = value
    
    return ordered



def _refresh_roi_labeled_image(emr: Dict[str, Any]) -> bool:
    report = emr.get("report")
    if not isinstance(report, dict):
        return False

    existing_roi_image = _resolve_data_image_path(report.get("thermal_roi_labeled_image"))

    thermal_images = report.get("thermal_images")
    if isinstance(thermal_images, list):
        for item in thermal_images:
            item_text = str(item or "")
            if "thermal_roi_labeled" not in item_text:
                continue
            candidate = _resolve_data_image_path(item)
            if candidate is None:
                continue
            report["thermal_roi_labeled_image"] = item_text
            try:
                report["thermal_roi_labeled_rev"] = str(candidate.stat().st_mtime_ns)
            except Exception:
                pass
            emr["report"] = report
            return True

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
    if marked is not None and marked.name == "thermal_roi_labeled.png":
        marked = None
    if marked is None:
        thermal_images = report.get("thermal_images")
        if isinstance(thermal_images, list):
            for item in thermal_images:
                if str(item).endswith("thermal_roi_labeled.png"):
                    continue
                marked = _resolve_data_image_path(item)
                if marked is not None:
                    break
    if marked is None:
        if existing_roi_image is not None and existing_roi_image.exists() and existing_roi_image.is_file():
            try:
                report["thermal_roi_labeled_rev"] = str(existing_roi_image.stat().st_mtime_ns)
            except Exception:
                pass
            emr["report"] = report
        return False

    out_path = DATA_DIR / record_id / "thermal_roi_labeled.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generated = render_labeled_thermal_image(
        marked,
        {"analysis": {"roi_analysis": roi_analysis}},
        "roi_labeled",
        out_path=out_path,
    )
    if generated is None:
        if existing_roi_image is not None and existing_roi_image.exists() and existing_roi_image.is_file():
            try:
                report["thermal_roi_labeled_rev"] = str(existing_roi_image.stat().st_mtime_ns)
            except Exception:
                pass
            emr["report"] = report
        return False

    relative = str(Path(generated).relative_to(DATA_DIR))
    report["thermal_roi_labeled_image"] = relative
    try:
        report["thermal_roi_labeled_rev"] = str(Path(generated).stat().st_mtime_ns)
    except Exception:
        pass

    thermal_images = report.get("thermal_images")
    if isinstance(thermal_images, list) and relative not in thermal_images:
        thermal_images.append(relative)
    elif not isinstance(thermal_images, list):
        report["thermal_images"] = [relative]

    emr["report"] = report
    return True


def get_emr(emr_id: str, *, ensure_report_outputs: bool = True) -> Dict[str, Any]:
    path = _emr_path(emr_id)
    if not path.exists():
        raise EmrNotFoundError("emr_not_found")

    emr = _load_json(path)
    
    # Normalize EMR fields (extract metrics from report.analysis if missing)
    emr = _normalize_emr_fields(emr)
    
    updated = _refresh_roi_labeled_image(emr)
    report_file_updated = _ensure_report_outputs(emr) if ensure_report_outputs else False
    if updated or report_file_updated:
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

    # Apply field priority ordering: pdf_report_path before docx_report_path
    return _prioritize_report_paths(emr)


def update_emr(emr_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    emr = get_emr(emr_id, ensure_report_outputs=False)
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
            # Force regeneration so PDF/DOCX reflects the latest diagnosis &
            # doctor_opinion (which may have just been updated by the AI step).
            for _path_key in ("pdf_report_path", "docx_report_path"):
                emr.pop(_path_key, None)
                report.pop(_path_key, None)
            _generate_report_outputs(report, emr, require_primary=False)
        except Exception:
            emr.setdefault("warnings", []).append("report_generate_failed")

    with open(_emr_path(emr_id), "w", encoding="utf-8") as handle:
        json.dump(emr, handle, ensure_ascii=False, indent=2)

    save_emr(emr)
    return _prioritize_report_paths(emr)


def archive_emr(emr_id: str, archived: bool = True) -> Dict[str, Any]:
    emr = get_emr(emr_id)
    emr["archived"] = archived

    with open(_emr_path(emr_id), "w", encoding="utf-8") as handle:
        json.dump(emr, handle, ensure_ascii=False, indent=2)

    save_emr(emr)
    return _prioritize_report_paths(emr)


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
        emrs.append(_prioritize_report_paths(data))

    emrs.sort(key=lambda item: item.get("created_at") or "")
    return emrs
