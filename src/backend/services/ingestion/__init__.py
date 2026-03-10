"""
Data ingestion service.

Handles device data import, quality control, and initial processing.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

from src.backend.core.config import settings
from src.backend.core.exceptions import ValidationError
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend" / "device-ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class IngestionService:
    """Service for ingesting thermal imaging data from devices."""
    
    def __init__(self):
        self.data_dir = settings.DATA_DIR
        
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
        logger.info("Ingesting data from %s", data_file)
        if not data_file.exists() or not data_file.is_file():
            raise ValidationError(f"Data file not found: {data_file}")

        try:
            legacy_models = importlib.import_module("app.models")
            legacy_qc = importlib.import_module("app.qc")
            legacy_storage = importlib.import_module("app.storage")

            parsed = legacy_models.IngestMetadata.model_validate(metadata)
            if validate:
                issues = legacy_qc.run_qc(parsed)
                if issues:
                    raise ValidationError("QC validation failed", details={"issues": issues})

            file_bytes = data_file.read_bytes()
            result = legacy_storage.save_payload(data_file.name, file_bytes, parsed.model_dump())
            return str(result.get("record_id") or "")
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Ingestion failed: {exc}") from exc

    def ingest_capture_dir(self, capture_path: str, move_to_processed: bool = True) -> Dict[str, Any]:
        capture_dir = Path(capture_path)
        if not capture_dir.exists() or not capture_dir.is_dir():
            raise FileNotFoundError("capture_path_not_found")
        legacy_device_connector = importlib.import_module("app.device_connector")
        result = legacy_device_connector.ingest_capture_dir(capture_dir)
        if move_to_processed:
            legacy_device_connector.move_capture_dir(capture_dir)
        return {"ingested": [result], "skipped": []}

    def ingest_pending_captures(self, move_to_processed: bool = True) -> Dict[str, Any]:
        legacy_device_connector = importlib.import_module("app.device_connector")
        return legacy_device_connector.ingest_pending_captures(move_to_processed=move_to_processed)


__all__ = ["IngestionService"]
