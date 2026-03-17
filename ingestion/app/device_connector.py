import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    ALLOWED_EXTENSIONS,
    DATA_DIR,
    DEVICE_DROP_DIR,
    DEVICE_POLL_INTERVAL_SEC,
    DEVICE_PROCESSED_DIR,
)
from .models import IngestMetadata
from .qc import run_qc
from .data_platform import get_patient, list_patients, update_record_images
from .storage import save_batch_payload, save_payload


_DEFAULT_PATIENT_DROP_DIR = Path(__file__).resolve().parents[2] / "data" / "patient"
PATIENT_DROP_DIR = Path(os.getenv("PATIENT_DROP_DIR", str(_DEFAULT_PATIENT_DROP_DIR)))
PATIENT_PROCESSED_DIR = DEVICE_PROCESSED_DIR / "patient"
PATIENT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
logger = logging.getLogger(__name__)
_EMR_MODULE = None
_PATIENT_FOLDER_STATE_FILE = ".analysis_state.json"

# Patient folder continuous monitoring state
_current_patient_folder: Optional[Path] = None
_current_patient_folder_file_count = 0


# Backend API base URL for notifications
_BACKEND_API_BASE = os.getenv("BACKEND_API_BASE", "http://localhost:8000")


async def _send_emr_notification(record_id: str, emr_id: str, patient_id: str):
    """Send EMR generation notification to backend (best effort)."""
    try:
        import urllib.request
        import json as json_lib
        
        backend_url = f"{_BACKEND_API_BASE}/ws-notify/emr-generated"
        payload = json_lib.dumps({
            "record_id": record_id,
            "emr_id": emr_id,
            "patient_id": patient_id,
        }).encode('utf-8')
        
        request = urllib.request.Request(
            backend_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        # Use urllib with a short timeout
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status == 200:
                logger.info(
                    "sent emr notification to backend record_id=%s emr_id=%s",
                    record_id,
                    emr_id,
                )
    except Exception as exc:
        # Silently fail - notifications are best-effort
        logger.debug("failed to send emr notification: %s", exc)


def _data_exts() -> set[str]:
    return {
        ext
        for ext in ALLOWED_EXTENSIONS
        if ext.lower() not in _IMAGE_EXTS
    }


def _get_emr_module():
    global _EMR_MODULE
    if _EMR_MODULE is None:
        from . import emr as emr_module

        _EMR_MODULE = emr_module
    return _EMR_MODULE


def _auto_generate_emr_report(record_id: str) -> Dict:
    """Generate EMR and report outputs immediately after successful ingestion.
    
    Returns a dict with:
    - status: "generated" or "failed"
    - emr_id: generated EMR ID (if successful)
    - patient_id: patient ID (if successful)
    - pdf_report_path: path to generated PDF (if successful)
    - error: error message (if failed)
    """
    try:
        emr_module = _get_emr_module()
        emr_result = emr_module.generate_emr(record_id, force=False, enable_roi=True, enable_llm=False)

        report = emr_result.get("report") if isinstance(emr_result, dict) else {}
        patient_info = emr_result.get("patient") if isinstance(emr_result, dict) else {}
        
        return {
            "status": "generated",
            "emr_id": emr_result.get("emr_id") if isinstance(emr_result, dict) else None,
            "record_id": record_id,
            "patient_id": patient_info.get("patient_id") if isinstance(patient_info, dict) else None,
            "pdf_report_path": (emr_result.get("pdf_report_path") if isinstance(emr_result, dict) else None)
            or (report.get("pdf_report_path") if isinstance(report, dict) else None),
        }
    except Exception as exc:
        logger.exception("auto emr/pdf generation failed record_id=%s error=%s", record_id, exc)
        return {
            "status": "failed",
            "error": str(exc),
        }


class DeviceCaptureError(RuntimeError):
    pass


def _find_data_file(capture_dir: Path) -> Optional[Path]:
    for item in capture_dir.iterdir():
        if (
            item.is_file()
            and item.suffix.lower() in ALLOWED_EXTENSIONS
            and item.suffix.lower() not in _IMAGE_EXTS
        ):
            return item
    return None


def _find_image_files(capture_dir: Path) -> List[Path]:
    return [
        item
        for item in capture_dir.iterdir()
        if item.is_file() and item.suffix.lower() in _IMAGE_EXTS
    ]


def _find_data_files(capture_dir: Path) -> List[Path]:
    data_exts = _data_exts()
    return [
        item
        for item in sorted(capture_dir.iterdir(), key=lambda p: p.name)
        if item.is_file() and item.suffix.lower() in data_exts
    ]


def _build_patient_folder_signature(patient_dir: Path) -> str:
    """Build a stable signature from data files so unchanged folders can be skipped."""
    digest = hashlib.sha256()
    for file_path in _find_data_files(patient_dir):
        try:
            stat = file_path.stat()
            digest.update(file_path.name.encode("utf-8", errors="ignore"))
            digest.update(b"|")
            digest.update(str(stat.st_size).encode("utf-8"))
            digest.update(b"|")
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
            digest.update(b";")
        except FileNotFoundError:
            continue
    return digest.hexdigest()


def _read_patient_folder_state(patient_dir: Path) -> Dict[str, Any]:
    state_path = patient_dir / _PATIENT_FOLDER_STATE_FILE
    if not state_path.exists():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_patient_folder_state(
    patient_dir: Path,
    *,
    signature: str,
    record_id: str,
    emr_id: str,
) -> None:
    state_path = patient_dir / _PATIENT_FOLDER_STATE_FILE
    payload = {
        "signature": signature,
        "record_id": record_id,
        "emr_id": emr_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("failed_to_write_folder_state folder=%s error=%s", patient_dir, exc)


def _patient_folder_needs_analysis(patient_dir: Path) -> Tuple[bool, str]:
    """Return (needs_analysis, signature)."""
    signature = _build_patient_folder_signature(patient_dir)
    state = _read_patient_folder_state(patient_dir)
    saved_signature = str(state.get("signature") or "").strip()
    return saved_signature != signature, signature


def _load_metadata(capture_dir: Path) -> Dict:
    metadata_path = capture_dir / "metadata.json"
    if not metadata_path.exists():
        raise DeviceCaptureError("metadata_missing")
    with open(metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compact_dict(data: Dict) -> Dict:
    return {key: value for key, value in data.items() if value is not None}


def _normalize_legacy_metadata(raw: Dict, capture_dir: Path) -> Dict:
    if "device" in raw and "capture" in raw:
        return raw

    resolution = raw.get("resolution")
    if isinstance(resolution, (list, tuple)) and len(resolution) == 2:
        resolution_value = f"{resolution[0]}x{resolution[1]}"
    else:
        resolution_value = resolution

    device_id = raw.get("device_id") or raw.get("device") or f"legacy-{capture_dir.name}"

    device = _compact_dict(
        {
            "device_id": str(device_id),
            "model": raw.get("device_model") or raw.get("model"),
            "firmware": raw.get("firmware"),
        }
    )

    capture_time = raw.get("capture_time")
    if not capture_time:
        capture_time = datetime.now().isoformat(timespec="seconds")

    capture = _compact_dict(
        {
            "capture_time": capture_time,
            "frame_rate_hz": raw.get("frame_rate_hz"),
            "resolution": resolution_value,
            "spectral_range": raw.get("spectral_range"),
            "distance_m": raw.get("distance_m"),
            "emissivity": raw.get("emissivity"),
        }
    )

    environment = _compact_dict(
        {
            "ambient_temp_c": raw.get("ambient_temperature_c") or raw.get("ambient_temp_c"),
            "humidity_percent": raw.get("humidity_percent"),
            "airflow": raw.get("airflow"),
        }
    )

    subject = raw.get("subject") or {}
    patient = raw.get("patient") or {}
    if not patient and subject:
        patient = _compact_dict(
            {
                "gender": subject.get("gender"),
                "age": subject.get("age"),
                "body_part": subject.get("body_part"),
                "posture": subject.get("posture"),
            }
        )

    normalized = {
        "device": device,
        "capture": capture,
        "environment": environment or None,
        "patient": patient or None,
        "clinical": raw.get("clinical"),
        "tags": raw.get("tags"),
    }
    return normalized


def _unique_processed_path(capture_dir: Path) -> Path:
    candidate = DEVICE_PROCESSED_DIR / capture_dir.name
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        candidate = DEVICE_PROCESSED_DIR / f"{capture_dir.name}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def _unique_processed_path_under(base_dir: Path, source_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    candidate = base_dir / source_dir.name
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        candidate = base_dir / f"{source_dir.name}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def move_capture_dir(capture_dir: Path) -> Path:
    target = _unique_processed_path(capture_dir)
    shutil.move(str(capture_dir), str(target))
    return target


def move_patient_dir(patient_dir: Path) -> Path:
    target = _unique_processed_path_under(PATIENT_PROCESSED_DIR, patient_dir)
    shutil.move(str(patient_dir), str(target))
    return target


def _default_patient_metadata(patient_dir: Path) -> Dict:
    now_iso = datetime.now().isoformat(timespec="seconds")
    patient_info = _resolve_patient_info_from_folder(patient_dir)
    patient_name = patient_info.get("name") or patient_dir.name
    patient_id = patient_info.get("patient_id") or patient_dir.name
    patient_gender = patient_info.get("gender")
    patient_age = patient_info.get("age")
    return {
        "device": {
            "device_id": f"folder-{patient_name}",
        },
        "capture": {
            "capture_time": now_iso,
        },
        "patient": {
            "patient_id": patient_id,
            "name": patient_name,
            "gender": patient_gender,
            "age": patient_age,
        },
    }


def _extract_patient_id_tokens(folder_name: str) -> List[str]:
    raw = str(folder_name or "").strip()
    if not raw:
        return []
    tokens = [raw]
    tokens.extend(re.findall(r"P[A-Z0-9]{6,}", raw.upper()))
    deduped: List[str] = []
    for token in tokens:
        if token and token not in deduped:
            deduped.append(token)
    return deduped


def _resolve_patient_info_from_folder(patient_dir: Path) -> Dict:
    """
    Resolve patient identity for auto-ingested folders.

    Priority:
    1) folder name or embedded token matches an existing patient_id.
    2) fallback to latest active patient (updated_at DESC), suitable for the
       common workflow: mini-program registration immediately followed by capture.
    """
    folder_name = patient_dir.name

    for token in _extract_patient_id_tokens(folder_name):
        try:
            patient = get_patient(token)
        except Exception:
            patient = None
        if patient:
            return {
                "patient_id": str(patient.get("patient_id") or "").strip(),
                "name": str(patient.get("name") or "").strip() or folder_name,
                "gender": patient.get("gender"),
                "age": patient.get("age"),
            }

    try:
        latest = list_patients(limit=1, offset=0, include_archived=False)
    except Exception:
        latest = []

    if latest:
        patient = latest[0] or {}
        pid = str(patient.get("patient_id") or "").strip()
        if pid:
            return {
                "patient_id": pid,
                "name": str(patient.get("name") or "").strip() or folder_name,
                "gender": patient.get("gender"),
                "age": patient.get("age"),
            }

    return {
        "patient_id": folder_name,
        "name": folder_name,
        "gender": None,
        "age": None,
    }


def ingest_patient_dir(patient_dir: Path) -> Dict:
    metadata_path = patient_dir / "metadata.json"
    if metadata_path.exists():
        metadata = _load_metadata(patient_dir)
        normalized = _normalize_legacy_metadata(metadata, patient_dir)
        patient = normalized.get("patient") if isinstance(normalized, dict) else None
        if not isinstance(patient, dict) or not str(patient.get("patient_id") or "").strip():
            resolved = _resolve_patient_info_from_folder(patient_dir)
            normalized["patient"] = {
                **(patient or {}),
                "patient_id": resolved.get("patient_id"),
                "name": resolved.get("name"),
                "gender": resolved.get("gender"),
                "age": resolved.get("age"),
            }
    else:
        normalized = _default_patient_metadata(patient_dir)

    parsed = IngestMetadata.model_validate(normalized)
    qc_issues = run_qc(parsed)

    data_files = _find_data_files(patient_dir)
    if not data_files:
        raise DeviceCaptureError("data_file_missing")

    primary_data = data_files[0]
    extra_data = [
        (item.name, item.read_bytes())
        for item in data_files[1:]
    ]
    image_data = [
        (item.name, item.read_bytes())
        for item in _find_image_files(patient_dir)
    ]

    result = save_batch_payload(
        primary_data.name,
        primary_data.read_bytes(),
        parsed.model_dump(),
        extra_data_files=extra_data or None,
        image_files=image_data or None,
    )

    image_paths = result.get("image_paths") or []
    if image_paths:
        update_record_images(result["record_id"], image_paths)

    return {
        **result,
        "patient_folder": str(patient_dir),
        "data_file_count": len(data_files),
        "image_file_count": len(image_data),
        "qc_issues": qc_issues,
    }


def ingest_capture_dir(capture_dir: Path) -> Dict:
    metadata = _load_metadata(capture_dir)
    normalized = _normalize_legacy_metadata(metadata, capture_dir)
    parsed = IngestMetadata.model_validate(normalized)

    data_file = _find_data_file(capture_dir)
    if not data_file:
        raise DeviceCaptureError("data_file_missing")

    file_bytes = data_file.read_bytes()
    qc_issues = run_qc(parsed)
    result = save_payload(data_file.name, file_bytes, parsed.model_dump())

    record_dir = DATA_DIR / result["record_id"]
    image_paths: List[str] = []
    for image_file in _find_image_files(capture_dir):
        target = record_dir / image_file.name
        shutil.copy2(image_file, target)
        image_paths.append(str(target))

    if image_paths:
        update_record_images(result["record_id"], image_paths)

    return {
        **result,
        "capture_path": str(capture_dir),
        "qc_issues": qc_issues,
        "image_paths": image_paths,
    }


def scan_device_drop(
    drop_dir: Path = DEVICE_DROP_DIR,
) -> Tuple[List[Path], List[str]]:
    pending: List[Path] = []
    skipped: List[str] = []

    for item in drop_dir.iterdir():
        if not item.is_dir():
            continue
        if (item / "metadata.json").exists() and _find_data_file(item):
            pending.append(item)
        else:
            skipped.append(str(item))

    return pending, skipped


def ingest_pending_captures(move_to_processed: bool = True) -> Dict:
    pending, skipped = scan_device_drop()
    ingested = []

    for capture_dir in pending:
        try:
            result = ingest_capture_dir(capture_dir)
            record_id = str(result.get("record_id") or "")
            if record_id:
                result["auto_emr"] = _auto_generate_emr_report(record_id)
            ingested.append(result)
            if move_to_processed:
                move_capture_dir(capture_dir)
        except DeviceCaptureError:
            skipped.append(str(capture_dir))

    return {
        "ingested": ingested,
        "skipped": skipped,
    }


def scan_patient_drop(patient_root: Path = PATIENT_DROP_DIR) -> Tuple[List[Path], List[str]]:
    pending: List[Path] = []
    skipped: List[str] = []

    if not patient_root.exists() or not patient_root.is_dir():
        return pending, skipped

    for item in patient_root.iterdir():
        if not item.is_dir():
            continue
        if _find_data_files(item):
            pending.append(item)
        else:
            skipped.append(str(item))

    return pending, skipped


def ingest_pending_patient_folders(move_to_processed: bool = True) -> Dict:
    pending, skipped = scan_patient_drop()
    ingested = []

    for patient_dir in pending:
        try:
            result = ingest_patient_dir(patient_dir)
            record_id = str(result.get("record_id") or "")
            if record_id:
                result["auto_emr"] = _auto_generate_emr_report(record_id)
            ingested.append(result)
            if move_to_processed:
                move_patient_dir(patient_dir)
        except DeviceCaptureError:
            skipped.append(str(patient_dir))

    return {
        "ingested": ingested,
        "skipped": skipped,
    }


def import_history_dir(root_dir: Path) -> Dict:
    if not root_dir.exists() or not root_dir.is_dir():
        raise DeviceCaptureError("history_root_not_found")

    ingested = []
    skipped: List[str] = []

    for item in root_dir.iterdir():
        if not item.is_dir():
            continue
        if (item / "metadata.json").exists() and _find_data_file(item):
            try:
                ingested.append(ingest_capture_dir(item))
            except DeviceCaptureError:
                skipped.append(str(item))
        else:
            skipped.append(str(item))

    return {
        "ingested": ingested,
        "skipped": skipped,
    }


async def poll_device_drop(stop_event: asyncio.Event) -> None:
    global _current_patient_folder, _current_patient_folder_file_count

    while not stop_event.is_set():
        ingest_pending_captures()

        # Priority 1: Check if current patient folder has new files added
        if (
            _current_patient_folder
            and _current_patient_folder.exists()
            and _current_patient_folder.is_dir()
        ):
            current_data_files = _find_data_files(_current_patient_folder)
            current_file_count = len(current_data_files)
            needs_analysis, current_signature = _patient_folder_needs_analysis(_current_patient_folder)

            # Re-ingest only when folder contents have changed.
            if needs_analysis:
                logger.info(
                    "detected_folder_change folder=%s old_count=%d new_count=%d",
                    _current_patient_folder.name,
                    _current_patient_folder_file_count,
                    current_file_count,
                )
                try:
                    result = ingest_patient_dir(_current_patient_folder)
                    record_id = str(result.get("record_id") or "")
                    emr_id = ""
                    if record_id:
                        emr_result = _auto_generate_emr_report(record_id)
                        result["auto_emr"] = emr_result
                        emr_id = str(emr_result.get("emr_id") or "")
                        
                        # Send notification if EMR generation was successful
                        if emr_result.get("status") == "generated":
                            patient_id = str(emr_result.get("patient_id") or "")
                            if emr_id and patient_id:
                                await _send_emr_notification(record_id, emr_id, patient_id)

                    _write_patient_folder_state(
                        _current_patient_folder,
                        signature=current_signature,
                        record_id=record_id,
                        emr_id=emr_id,
                    )
                    
                    _current_patient_folder_file_count = current_file_count
                    logger.info(
                        "re_ingested_patient_folder=%s record_id=%s",
                        _current_patient_folder.name,
                        record_id,
                    )
                except DeviceCaptureError as e:
                    logger.warning(
                        "failed_to_reingest patient_folder=%s error=%s",
                        _current_patient_folder.name,
                        e,
                    )

                # Continue monitoring current folder
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=DEVICE_POLL_INTERVAL_SEC
                    )
                except asyncio.TimeoutError:
                    continue
                continue

        # Priority 2: Scan for new patient folders
        pending, skipped = scan_patient_drop()

        if pending:
            # Prefer folders that changed since last successful analysis.
            changed_candidates: List[Tuple[Path, str]] = []
            for folder in pending:
                needs_analysis, signature = _patient_folder_needs_analysis(folder)
                if needs_analysis:
                    changed_candidates.append((folder, signature))

            if not changed_candidates:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=DEVICE_POLL_INTERVAL_SEC)
                except asyncio.TimeoutError:
                    continue
                continue

            # New/changed patient folder(s) detected, switch to first changed one
            new_patient_dir, new_signature = changed_candidates[0]
            new_data_files = _find_data_files(new_patient_dir)

            logger.info(
                "switching_to_new_patient_folder folder=%s file_count=%d",
                new_patient_dir.name,
                len(new_data_files),
            )

            try:
                result = ingest_patient_dir(new_patient_dir)
                record_id = str(result.get("record_id") or "")
                emr_id = ""
                if record_id:
                    emr_result = _auto_generate_emr_report(record_id)
                    result["auto_emr"] = emr_result
                    emr_id = str(emr_result.get("emr_id") or "")
                    
                    # Send notification if EMR generation was successful
                    if emr_result.get("status") == "generated":
                        patient_id = str(emr_result.get("patient_id") or "")
                        if emr_id and patient_id:
                            await _send_emr_notification(record_id, emr_id, patient_id)

                _write_patient_folder_state(
                    new_patient_dir,
                    signature=new_signature,
                    record_id=record_id,
                    emr_id=emr_id,
                )

                # Update state to track this new folder
                _current_patient_folder = new_patient_dir
                _current_patient_folder_file_count = len(new_data_files)

                logger.info(
                    "ingested_new_patient_folder=%s record_id=%s",
                    new_patient_dir.name,
                    record_id,
                )
            except DeviceCaptureError as e:
                logger.warning(
                    "failed_to_ingest new patient_folder=%s error=%s",
                    new_patient_dir.name,
                    e,
                )
                # Still track it to avoid re-scanning same failed folder
                _current_patient_folder = new_patient_dir
                _current_patient_folder_file_count = len(new_data_files)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=DEVICE_POLL_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue
