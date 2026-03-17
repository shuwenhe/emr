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


def save_batch_payload(
    primary_file_name: str,
    primary_file_bytes: bytes,
    metadata: Dict,
    extra_data_files: List[tuple] | None = None,  # list of (filename, bytes)
    image_files: List[tuple] | None = None,        # list of (filename, bytes)
) -> Dict:
    """
    Ingest a batch of files for the same patient into a single record.

    The first .dat/.csv file is treated as the primary data source and
    converted / inserted into ClickHouse as usual.  All additional data
    files and image files are stored alongside it in the same record
    directory so that the report pipeline has access to all of them.

    Returns the same dict as save_payload plus:
      - extra_data_paths: list of paths for supplementary data files
      - image_paths: list of paths for image files
    """
    record_id = str(uuid.uuid4())
    record_path = _record_dir(record_id)

    # -- primary data file --
    primary_path = record_path / primary_file_name
    primary_path.write_bytes(primary_file_bytes)

    # -- build image path list (write files first) --
    saved_image_paths: List[str] = []
    if image_files:
        images_dir = record_path / "images"
        images_dir.mkdir(exist_ok=True)
        for img_name, img_bytes in image_files:
            img_path = images_dir / img_name
            img_path.write_bytes(img_bytes)
            saved_image_paths.append(str(img_path))

    # -- save metadata + record row --
    meta_path = record_path / "metadata.json"
    meta_dict = dict(metadata)
    if saved_image_paths:
        meta_dict["image_paths"] = saved_image_paths

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, ensure_ascii=False, indent=2)

    save_record(record_id, meta_dict, str(primary_path), saved_image_paths or None)

    # -- extra data files --
    extra_data_paths: List[str] = []
    if extra_data_files:
        for extra_name, extra_bytes in extra_data_files:
            extra_path = record_path / extra_name
            extra_path.write_bytes(extra_bytes)
            extra_data_paths.append(str(extra_path))

    # -- convert primary file and insert into ClickHouse --
    csv_targets: List[Path] = []
    matrix_csv_path: Path | None = None
    suffix = primary_path.suffix.lower()
    if suffix == ".csv":
        csv_targets.append(primary_path)
    elif suffix == ".dat":
        try:
            matrix_csv_path = _convert_dat_to_matrix_csv(primary_path, metadata)
            csv_targets.append(matrix_csv_path)
        except Exception as exc:
            logging.warning("DAT conversion skipped for %s: %s", primary_path.name, exc)

    # also convert supplementary .dat/.csv files
    for extra_str in extra_data_paths:
        extra_p = Path(extra_str)
        esuffix = extra_p.suffix.lower()
        if esuffix == ".csv":
            csv_targets.append(extra_p)
        elif esuffix == ".dat":
            try:
                extra_csv = _convert_dat_to_matrix_csv(extra_p, metadata)
                csv_targets.append(extra_csv)
            except Exception as exc:
                logging.warning("DAT conversion skipped for %s: %s", extra_p.name, exc)

    for idx, csv_path in enumerate(csv_targets):
        try:
            insert_thermal_csv(
                record_id=record_id,
                metadata=metadata,
                data_path=str(csv_path),
                frame_id=csv_path.stem,
            )
        except Exception as exc:
            logging.warning("ClickHouse ingest skipped for frame %s: %s", idx, exc)

    return {
        "record_id": record_id,
        "storage_path": str(primary_path),
        "matrix_csv_path": str(matrix_csv_path) if matrix_csv_path else None,
        "extra_data_paths": extra_data_paths,
        "image_paths": saved_image_paths,
    }
