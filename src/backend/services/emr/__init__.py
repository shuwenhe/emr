"""
EMR (Electronic Medical Record) service.

Patient and EMR record management.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.backend.core.config import settings
from src.backend.core.exceptions import EMRNotFoundError
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[4] / "ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class EMRService:
    """Service for managing electronic medical records."""
    
    # Cache imported modules at class level
    _legacy_emr = None
    
    def __init__(self):
        self.emr_dir = settings.EMR_DIR
        # Lazy load module on first use
        if EMRService._legacy_emr is None:
            EMRService._legacy_emr = importlib.import_module("app.emr")
        
    def create_emr(
        self,
        record_id: str,
        patient_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new EMR record.
        
        Args:
            record_id: Thermal data record ID
            patient_id: Patient identifier (optional)
            metadata: Additional metadata
            
        Returns:
            Created EMR record
        """
        logger.info("Creating EMR for record %s", record_id)
        try:
            legacy_emr = self._legacy_emr
            return legacy_emr.generate_emr(record_id, force=False)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise EMRNotFoundError(f"Failed to create EMR for {record_id}: {exc}") from exc
    
    def get_emr(self, emr_id: str) -> Dict[str, Any]:
        """
        Retrieve an EMR record.
        
        Args:
            emr_id: EMR identifier
            
        Returns:
            EMR record
            
        Raises:
            EMRNotFoundError: If EMR not found
        """
        logger.info("Retrieving EMR %s", emr_id)
        legacy_emr = self._legacy_emr
        legacy_not_found = getattr(legacy_emr, "EmrNotFoundError", FileNotFoundError)
        try:
            return legacy_emr.get_emr(emr_id)
        except legacy_not_found as exc:
            raise EMRNotFoundError(str(exc)) from exc
    
    def list_emrs(
        self,
        patient_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List EMR records.
        
        Args:
            patient_id: Filter by patient ID
            limit: Maximum number of records
            offset: Pagination offset
            
        Returns:
            List of EMR records
        """
        logger.info("Listing EMRs (patient=%s, limit=%s, offset=%s)", patient_id, limit, offset)
        try:
            legacy_emr = self._legacy_emr
            items = legacy_emr.list_emrs(patient_id=patient_id, include_archived=False)
            start = max(0, offset)
            end = start + max(0, limit)
            return items[start:end]
        except Exception as exc:
            raise EMRNotFoundError(f"Failed to list EMRs: {exc}") from exc

    def update_emr(self, emr_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Updating EMR %s", emr_id)
        try:
            legacy_emr = self._legacy_emr
            return legacy_emr.update_emr(emr_id, updates)
        except Exception as exc:
            raise EMRNotFoundError(f"Failed to update EMR {emr_id}: {exc}") from exc

    def archive_emr(self, emr_id: str, archived: bool = True) -> Dict[str, Any]:
        logger.info("Archiving EMR %s (archived=%s)", emr_id, archived)
        try:
            legacy_emr = self._legacy_emr
            return legacy_emr.archive_emr(emr_id, archived)
        except Exception as exc:
            raise EMRNotFoundError(f"Failed to archive EMR {emr_id}: {exc}") from exc


__all__ = ["EMRService"]
