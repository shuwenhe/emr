import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List

from .config import DATA_DIR
from .data_platform import save_record
from .clickhouse_store import insert_thermal_csv


def _record_dir(record_id: str) -> Path:
    record_path = DATA_DIR / record_id
    record_path.mkdir(parents=True, exist_ok=True)
    return record_path


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

    if data_path.suffix.lower() == ".csv":
        try:
            insert_thermal_csv(
                record_id=record_id,
                metadata=metadata,
                data_path=str(data_path),
                frame_id=data_path.stem,
            )
        except Exception as exc:
            logging.warning("ClickHouse ingest skipped: %s", exc)

    return {
        "record_id": record_id,
        "storage_path": str(data_path),
    }
