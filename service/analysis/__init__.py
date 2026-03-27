"""
Analysis service.

Thermal data analysis, ROI detection, and temperature metrics calculation.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any, Dict

from core.config import settings
from core.exceptions import AnalysisError
from core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[2] / "ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class AnalysisService:
    """Service for analyzing thermal imaging data."""
    
    # Cache imported modules at class level
    _legacy_analysis = None
    
    def __init__(self):
        self.data_dir = settings.DATA_DIR
        if AnalysisService._legacy_analysis is None:
            AnalysisService._legacy_analysis = importlib.import_module("app.analysis")
        
    def analyze_record(
        self,
        record_id: str,
        *,
        enable_roi: bool = True,
        enable_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze a thermal imaging record.
        
        Args:
            record_id: Record identifier
            enable_roi: Enable ROI (Region of Interest) detection
            enable_llm: Enable LLM-powered analysis
            
        Returns:
            Analysis results including:
            - temperature_metrics: Min/max/avg temperatures
            - roi_analysis: Detected body regions
            - regional_comparison: Abnormal regions
            - risk_level: Overall risk assessment
            
        Raises:
            AnalysisError: If analysis fails
        """
        logger.info("[步骤2-分析] 开始热成像分析 record_id=%s roi=%s llm=%s", record_id, enable_roi, enable_llm)
        t0 = time.time()
        try:
            result = self._legacy_analysis.analyze_record(
                record_id,
                enable_roi=enable_roi,
                enable_llm=enable_llm,
            )
            elapsed = time.time() - t0
            risk = (
                (result.get("report") or {}).get("analysis", {}).get("risk_level", "unknown")
                if isinstance(result, dict) else "unknown"
            )
            logger.info(
                "[步骤2-分析] 分析完成 record_id=%s risk_level=%s 耗时=%.2fs",
                record_id, risk, elapsed,
            )
            return result
        except FileNotFoundError:
            logger.warning("[步骤2-分析] 记录不存在 record_id=%s", record_id)
            raise
        except Exception as exc:
            logger.exception("[步骤2-分析] 分析失败 record_id=%s error=%s", record_id, exc)
            raise AnalysisError(f"Analysis failed for record {record_id}: {exc}") from exc


__all__ = ["AnalysisService"]
