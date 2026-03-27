"""
EMR (Electronic Medical Record) service.

Patient and EMR record management.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import settings
from core.exceptions import EMRNotFoundError
from core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[2] / "ingestion"
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
        *,
        enable_roi: bool = True,
        enable_llm: bool = True,
        ensure_report_outputs: bool = True,
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
        logger.info(
            "[步骤3-EMR] 开始生成电子病历 record_id=%s patient_id=%s roi=%s llm=%s ensure_outputs=%s",
            record_id,
            patient_id,
            enable_roi,
            enable_llm,
            ensure_report_outputs,
        )
        try:
            legacy_emr = self._legacy_emr
            result = legacy_emr.generate_emr(
                record_id,
                force=False,
                enable_roi=enable_roi,
                enable_llm=enable_llm,
                ensure_report_outputs=ensure_report_outputs,
            )
            emr_id = result.get("emr_id") if isinstance(result, dict) else None
            patient = (result.get("patient") or {}).get("name", "") if isinstance(result, dict) else ""
            pdf_report_path = result.get("pdf_report_path", "") if isinstance(result, dict) else ""
            docx_report_path = result.get("docx_report_path", "") if isinstance(result, dict) else ""
            if not pdf_report_path and isinstance(result, dict):
                report_obj = result.get("report")
                if isinstance(report_obj, dict):
                    pdf_report_path = report_obj.get("pdf_report_path", "")
            if not docx_report_path and isinstance(result, dict):
                report_obj = result.get("report")
                if isinstance(report_obj, dict):
                    docx_report_path = report_obj.get("docx_report_path", "")
            logger.info(
                "[步骤3-EMR] 病历生成完成 record_id=%s emr_id=%s patient=%s pdf_report_path=%s docx_report_path=%s",
                record_id, emr_id, patient, pdf_report_path, docx_report_path,
            )
            return result
        except FileNotFoundError:
            logger.warning("[步骤3-EMR] 记录不存在 record_id=%s", record_id)
            raise
        except Exception as exc:
            logger.exception("[步骤3-EMR] 病历生成失败 record_id=%s error=%s", record_id, exc)
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
        logger.info("[步骤3-EMR] 查询病历 emr_id=%s", emr_id)
        legacy_emr = self._legacy_emr
        legacy_not_found = getattr(legacy_emr, "EmrNotFoundError", FileNotFoundError)
        try:
            result = legacy_emr.get_emr(emr_id)
            patient = (result.get("patient") or {}).get("name", "") if isinstance(result, dict) else ""
            logger.info("[步骤3-EMR] 查询完成 emr_id=%s patient=%s", emr_id, patient)
            return result
        except legacy_not_found as exc:
            logger.warning("[步骤3-EMR] 病历不存在 emr_id=%s", emr_id)
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
