"""
Data ingestion service.

Handles device data import, quality control, and initial processing.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

from backend.core.config import settings
from backend.core.exceptions import ValidationError
from backend.core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[3] / "ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class IngestionService:
    """Service for ingesting thermal imaging data from devices."""
    
    # Cache imported modules at class level
    _legacy_models = None
    _legacy_qc = None
    _legacy_storage = None
    _legacy_device_connector = None
    
    def __init__(self):
        self.data_dir = settings.DATA_DIR
        # Lazy load modules on first use
        if IngestionService._legacy_models is None:
            IngestionService._legacy_models = importlib.import_module("app.models")
            IngestionService._legacy_qc = importlib.import_module("app.qc")
            IngestionService._legacy_storage = importlib.import_module("app.storage")
            IngestionService._legacy_device_connector = importlib.import_module("app.device_connector")
        
    def ingest_data(
        self,
        data_file: Path,
        metadata: Dict[str, Any],
        *,
        validate: bool = True,
    ) -> str:
        """
        Ingest thermal imaging data.
        
        Args:
            data_file: Path to thermal data file (CSV)
            metadata: Patient and device metadata
            validate: Whether to perform quality control checks
            
        Returns:
            Record ID for the ingested data
            
        Raises:
            ValidationError: If data validation fails
        """
        file_size_kb = data_file.stat().st_size / 1024 if data_file.exists() else 0
        logger.info("[步骤1-导入] 开始解析文件 file=%s size=%.1fKB", data_file.name, file_size_kb)
        if not data_file.exists() or not data_file.is_file():
            raise ValidationError(f"Data file not found: {data_file}")

        try:
            legacy_models = self._legacy_models
            legacy_qc = self._legacy_qc
            legacy_storage = self._legacy_storage

            parsed = legacy_models.IngestMetadata.model_validate(metadata)
            patient_name = getattr(parsed, 'name', None) or metadata.get('name', '未知')
            logger.info("[步骤1-导入] 元数据解析成功 patient=%s", patient_name)
            if validate:
                issues = legacy_qc.run_qc(parsed)
                if issues:
                    logger.warning("[步骤1-导入] QC检查失败 issues=%d patient=%s", len(issues), patient_name)
                    raise ValidationError("QC validation failed", details={"issues": issues})
                logger.info("[步骤1-导入] QC检查通过 patient=%s", patient_name)
            
            file_bytes = data_file.read_bytes()
            result = legacy_storage.save_payload(data_file.name, file_bytes, parsed.model_dump())
            record_id = str(result.get("record_id") or "")
            logger.info("[步骤1-导入] 存储成功 record_id=%s patient=%s", record_id, patient_name)
            return record_id
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Ingestion failed: {exc}") from exc

    def ingest_capture_dir(self, capture_path: str, move_to_processed: bool = True) -> Dict[str, Any]:
        capture_dir = Path(capture_path)
        if not capture_dir.exists() or not capture_dir.is_dir():
            raise FileNotFoundError("capture_path_not_found")
        logger.info("[步骤1-设备] 导入捕获目录 path=%s move=%s", capture_path, move_to_processed)
        legacy_device_connector = self._legacy_device_connector
        result = legacy_device_connector.ingest_capture_dir(capture_dir)
        if move_to_processed:
            legacy_device_connector.move_capture_dir(capture_dir)
        ingested = len(result) if isinstance(result, list) else 1
        logger.info("[步骤1-设备] 捕获目录导入完成 ingested=%d path=%s", ingested, capture_path)
        return {"ingested": [result], "skipped": []}

    def ingest_pending_captures(self, move_to_processed: bool = True) -> Dict[str, Any]:
        logger.info("[步骤1-设备] 扫描并导入所有待处理捕获 move=%s", move_to_processed)
        legacy_device_connector = self._legacy_device_connector
        result = legacy_device_connector.ingest_pending_captures(move_to_processed=move_to_processed)
        ingested = len(result.get("ingested", [])) if isinstance(result, dict) else 0
        skipped = len(result.get("skipped", [])) if isinstance(result, dict) else 0
        logger.info("[步骤1-设备] 待处理捕获导入完成 ingested=%d skipped=%d", ingested, skipped)
        return result


__all__ = ["IngestionService"]
