from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, Optional


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[2] / "ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class LegacyPlatformAdapter:
    _legacy_data_platform = None
    _legacy_device_connector = None
    _legacy_analysis = None

    def __init__(self):
        if LegacyPlatformAdapter._legacy_data_platform is None:
            LegacyPlatformAdapter._legacy_data_platform = importlib.import_module("app.data_platform")
            LegacyPlatformAdapter._legacy_device_connector = importlib.import_module("app.device_connector")
            LegacyPlatformAdapter._legacy_analysis = importlib.import_module("app.analysis")

    def init_db(self) -> None:
        self._legacy_data_platform.init_db()

    async def poll_device_drop(self, stop_event):
        await self._legacy_device_connector.poll_device_drop(stop_event)

    def import_history(self, root_path: str, analyze: bool = True) -> Dict[str, Any]:
        result = self._legacy_device_connector.import_history_dir(Path(root_path))
        if analyze:
            analyzed = []
            for item in result.get("ingested", []):
                record_id = item.get("record_id")
                if record_id:
                    analyzed.append(self._legacy_analysis.analyze_record(record_id))
            result["analyzed"] = analyzed
        return result

    def summary(self) -> Dict[str, Any]:
        return self._legacy_data_platform.summary()

    def list_records(self, patient_id: Optional[str] = None, limit: int = 50):
        return self._legacy_data_platform.list_records(patient_id=patient_id, limit=limit)

    def list_platform_emrs(
        self,
        patient_id: Optional[str] = None,
        record_id: Optional[str] = None,
        limit: int = 50,
        include_archived: bool = False,
    ):
        return self._legacy_data_platform.list_emrs(
            patient_id=patient_id,
            record_id=record_id,
            limit=limit,
            include_archived=include_archived,
        )

    def upsert_patient(self, payload: Dict[str, Any]) -> Optional[str]:
        return self._legacy_data_platform.upsert_patient(payload)

    def list_patients(
        self,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
        include_deleted: bool = False,
    ):
        return self._legacy_data_platform.list_patients(
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )

    def get_patient(self, patient_id: str):
        return self._legacy_data_platform.get_patient(patient_id)

    def update_patient(self, patient_id: str, payload: Dict[str, Any]):
        return self._legacy_data_platform.update_patient(patient_id, payload)

    def archive_patient(self, patient_id: str, archived: bool = True):
        return self._legacy_data_platform.archive_patient(patient_id, archived)

    def delete_patient(self, patient_id: str) -> bool:
        return self._legacy_data_platform.delete_patient(patient_id)

    def restore_deleted_patient(self, patient_id: str):
        return self._legacy_data_platform.restore_deleted_patient(patient_id)
