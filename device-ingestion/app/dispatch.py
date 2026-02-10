import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .analysis import analyze_record
from .config import DATA_DIR


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def dispatch_record(record_id: str) -> Dict[str, Any]:
    record_dir = DATA_DIR / record_id
    if not record_dir.exists():
        raise FileNotFoundError("record_not_found")

    dispatch_path = record_dir / "dispatch.json"
    if not dispatch_path.exists():
        analyze_record(record_id)

    dispatch_path = record_dir / "dispatch.json"
    if not dispatch_path.exists():
        raise FileNotFoundError("dispatch_not_found")

    dispatch_payload = _load_json(dispatch_path)
    ack = {
        "dispatch_id": dispatch_payload.get("dispatch_id"),
        "record_id": record_id,
        "status": "queued",
        "received_at": datetime.now().isoformat(timespec="seconds"),
    }

    ack_path = record_dir / "dispatch_ack.json"
    with open(ack_path, "w", encoding="utf-8") as handle:
        json.dump(ack, handle, indent=2, ensure_ascii=False)

    return {
        "dispatch": dispatch_payload,
        "ack": ack,
    }
