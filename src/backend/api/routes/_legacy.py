from __future__ import annotations

import importlib
import sys
from pathlib import Path

_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend" / "device-ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))

legacy_config = importlib.import_module("app.config")
legacy_analysis = importlib.import_module("app.analysis")
legacy_device_connector = importlib.import_module("app.device_connector")
legacy_data_platform = importlib.import_module("app.data_platform")
legacy_dispatch = importlib.import_module("app.dispatch")
legacy_emr = importlib.import_module("app.emr")
legacy_models = importlib.import_module("app.models")
legacy_qc = importlib.import_module("app.qc")
legacy_storage = importlib.import_module("app.storage")

ALLOWED_EXTENSIONS = legacy_config.ALLOWED_EXTENSIONS
MAX_FILE_MB = legacy_config.MAX_FILE_MB
REPORTS_DIR = legacy_config.REPORTS_DIR
DATA_DIR = legacy_config.DATA_DIR

AnalyzeRequest = legacy_models.AnalyzeRequest
DeviceIngestRequest = legacy_models.DeviceIngestRequest
DispatchRequest = legacy_models.DispatchRequest
EmrGenerateRequest = legacy_models.EmrGenerateRequest
EmrUpdateRequest = legacy_models.EmrUpdateRequest
EmrArchiveRequest = legacy_models.EmrArchiveRequest
HistoryImportRequest = legacy_models.HistoryImportRequest
IngestMetadata = legacy_models.IngestMetadata
PatientUpsertRequest = legacy_models.PatientUpsertRequest
PatientArchiveRequest = legacy_models.PatientArchiveRequest
PatientDeleteRequest = legacy_models.PatientDeleteRequest
ReportArchiveRequest = legacy_models.ReportArchiveRequest

EmrNotFoundError = legacy_emr.EmrNotFoundError
