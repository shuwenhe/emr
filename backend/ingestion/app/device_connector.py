import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import (
    ALLOWED_EXTENSIONS,
    DATA_DIR,
    DEVICE_DROP_DIR,
    DEVICE_POLL_INTERVAL_SEC,
    DEVICE_PROCESSED_DIR,
)
from .models import IngestMetadata
from .qc import run_qc
from .data_platform import update_record_images
from .storage import save_payload


class DeviceCaptureError(RuntimeError):
    pass


def _find_data_file(capture_dir: Path) -> Optional[Path]:
    image_exts = {".png", ".jpg", ".jpeg"}
    for item in capture_dir.iterdir():
        if (
            item.is_file()
            and item.suffix.lower() in ALLOWED_EXTENSIONS
            and item.suffix.lower() not in image_exts
        ):
            return item
    return None


def _find_image_files(capture_dir: Path) -> List[Path]:
    image_exts = {".png", ".jpg", ".jpeg"}
    return [
        item
        for item in capture_dir.iterdir()
        if item.is_file() and item.suffix.lower() in image_exts
    ]


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


def move_capture_dir(capture_dir: Path) -> Path:
    target = _unique_processed_path(capture_dir)
    shutil.move(str(capture_dir), str(target))
    return target


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
            ingested.append(result)
            if move_to_processed:
                move_capture_dir(capture_dir)
        except DeviceCaptureError:
            skipped.append(str(capture_dir))

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
    while not stop_event.is_set():
        ingest_pending_captures()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=DEVICE_POLL_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue
