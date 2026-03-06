import json
import logging
import uuid
import re
from pathlib import Path
from typing import Dict, List

import numpy as np

from .config import DATA_DIR
from .data_platform import save_record
from .clickhouse_store import insert_thermal_csv


def _record_dir(record_id: str) -> Path:
    record_path = DATA_DIR / record_id
    record_path.mkdir(parents=True, exist_ok=True)
    return record_path


def _parse_resolution(metadata: Dict) -> tuple[int | None, int | None]:
    capture = metadata.get("capture") if isinstance(metadata, dict) else None
    resolution = None
    if isinstance(capture, dict):
        resolution = capture.get("resolution")
    if not resolution:
        resolution = metadata.get("resolution") if isinstance(metadata, dict) else None
    if isinstance(resolution, str):
        match = re.search(r"(\d+)\s*[xX]\s*(\d+)", resolution)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def _reshape_temperatures(values: np.ndarray, width: int | None, height: int | None) -> np.ndarray:
    total = int(values.size)
    if width and height and width * height == total:
        return values.reshape((height, width))
    if width and height and height * width == total:
        return values.reshape((height, width))
    if width and total % width == 0:
        return values.reshape((total // width, width))
    if height and total % height == 0:
        return values.reshape((height, total // height))
    raise ValueError(f"cannot_reshape_temperature_sequence total={total} width={width} height={height}")


def _convert_dat_to_matrix_csv(data_path: Path, metadata: Dict) -> Path:
    raw_text = data_path.read_bytes().decode("latin1", errors="ignore")
    marker = "irdata:"
    marker_index = raw_text.find(marker)
    if marker_index < 0:
        raise ValueError("irdata_marker_not_found")

    header_text = raw_text[:marker_index]
    data_text = raw_text[marker_index + len(marker):]

    width = None
    height = None
    width_match = re.search(r"width\s*=\s*(\d+)", header_text, flags=re.IGNORECASE)
    height_match = re.search(r"height\s*=\s*(\d+)", header_text, flags=re.IGNORECASE)
    if width_match:
        width = int(width_match.group(1))
    if height_match:
        height = int(height_match.group(1))

    if not width or not height:
        width, height = _parse_resolution(metadata)

    cleaned_data_text = data_text.replace("\r", ",").replace("\n", ",").strip().strip(",")
    values = np.fromstring(cleaned_data_text, sep=",", dtype=np.float32)
    if values.size == 0:
        raise ValueError("temperature_values_not_found")

    matrix = _reshape_temperatures(values, width, height)
    matrix_csv_path = data_path.with_name(f"{data_path.stem}_matrix.csv")
    np.savetxt(matrix_csv_path, matrix, delimiter=",", fmt="%.2f")
    return matrix_csv_path


def save_payload(
    file_name: str,
    file_bytes: bytes,
    metadata: Dict,
    image_paths: List[str] | None = None,
) -> Dict:
    record_id = str(uuid.uuid4())
    record_path = _record_dir(record_id)

    data_path = record_path / file_name
    with open(data_path, "wb") as f:
        f.write(file_bytes)

    meta_path = record_path / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    save_record(record_id, metadata, str(data_path), image_paths)

    csv_targets: List[Path] = []
    matrix_csv_path: Path | None = None
    suffix = data_path.suffix.lower()
    if suffix == ".csv":
        csv_targets.append(data_path)
    elif suffix == ".dat":
        try:
            matrix_csv_path = _convert_dat_to_matrix_csv(data_path, metadata)
            csv_targets.append(matrix_csv_path)
        except Exception as exc:
            logging.warning("DAT conversion skipped for %s: %s", data_path.name, exc)

    for csv_path in csv_targets:
        try:
            insert_thermal_csv(
                record_id=record_id,
                metadata=metadata,
                data_path=str(csv_path),
                frame_id=csv_path.stem,
            )
        except Exception as exc:
            logging.warning("ClickHouse ingest skipped: %s", exc)

    return {
        "record_id": record_id,
        "storage_path": str(data_path),
        "matrix_csv_path": str(matrix_csv_path) if matrix_csv_path else None,
    }
