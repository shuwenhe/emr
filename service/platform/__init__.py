from __future__ import annotations

from typing import Any, Dict, Optional

from .legacy_adapter import LegacyPlatformAdapter
from .types import PlatformGateway


class PlatformService:
    def __init__(self, gateway: PlatformGateway | None = None):
        self._gateway = gateway or LegacyPlatformAdapter()
    
    def init_db(self) -> None:
        self._gateway.init_db()

    async def poll_device_drop(self, stop_event):
        await self._gateway.poll_device_drop(stop_event)

    def import_history(self, root_path: str, analyze: bool = True) -> Dict[str, Any]:
        return self._gateway.import_history(root_path=root_path, analyze=analyze)

    def summary(self) -> Dict[str, Any]:
        return self._gateway.summary()

    def list_records(self, patient_id: Optional[str] = None, limit: int = 50):
        return self._gateway.list_records(patient_id=patient_id, limit=limit)

    def list_platform_emrs(
        self,
        patient_id: Optional[str] = None,
        record_id: Optional[str] = None,
        limit: int = 50,
        include_archived: bool = False,
    ):
        return self._gateway.list_platform_emrs(
            patient_id=patient_id,
            record_id=record_id,
            limit=limit,
            include_archived=include_archived,
        )

    def upsert_patient(self, payload: Dict[str, Any]) -> Optional[str]:
        return self._gateway.upsert_patient(payload)

    def list_patients(
        self,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
        include_deleted: bool = False,
    ):
        return self._gateway.list_patients(
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            include_deleted=include_deleted,
        )

    def get_patient(self, patient_id: str):
        return self._gateway.get_patient(patient_id)

    def update_patient(self, patient_id: str, payload: Dict[str, Any]):
        return self._gateway.update_patient(patient_id, payload)

    def archive_patient(self, patient_id: str, archived: bool = True):
        return self._gateway.archive_patient(patient_id, archived)

    def delete_patient(self, patient_id: str) -> bool:
        return self._gateway.delete_patient(patient_id)

    def restore_deleted_patient(self, patient_id: str):
        return self._gateway.restore_deleted_patient(patient_id)


__all__ = ["PlatformService"]
