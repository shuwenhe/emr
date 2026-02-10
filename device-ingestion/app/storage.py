import json
import uuid
from pathlib import Path
from typing import Dict

from .config import DATA_DIR


def _record_dir(record_id: str) -> Path:
    record_path = DATA_DIR / record_id
    record_path.mkdir(parents=True, exist_ok=True)
    return record_path


def save_payload(file_name: str, file_bytes: bytes, metadata: Dict) -> Dict:
    record_id = str(uuid.uuid4())
    record_path = _record_dir(record_id)

    data_path = record_path / file_name
    with open(data_path, "wb") as f:
        f.write(file_bytes)

    meta_path = record_path / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return {
        "record_id": record_id,
        "storage_path": str(data_path),
    }
