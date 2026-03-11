"""
AI-powered services including LLM report generation and RAG.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from typing import Any, Dict

from core.config import settings
from core.exceptions import LLMError
from core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[2] / "ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class AIService:
    """Service for AI-powered features."""
    
    def __init__(self):
        self.llm_enabled = settings.LLM_ENABLED
        self.llm_provider = settings.LLM_PROVIDER
        self.llm_model = settings.LLM_MODEL
        
    def is_enabled(self) -> bool:
        """Check if LLM features are enabled."""
        return self.llm_enabled
    
    def generate_report_summary(
        self,
        report: Dict[str, Any],
        emr: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate AI-powered report summary and recommendations.
        
        Args:
            report: Report data
            emr: EMR context
            
        Returns:
            AI-generated content including:
            - treatment_plan_text: Treatment recommendations
            - report_note: Additional observations
            
        Raises:
            LLMError: If LLM generation fails
        """
        if not self.is_enabled():
            logger.warning("[步骤4-AI] LLM功能已禁用，跳过AI报告生成")
            return {}

        logger.info("[步骤4-AI] 开始AI报告生成 provider=%s model=%s", self.llm_provider, self.llm_model)
        t0 = time.time()
        try:
            legacy_llm = importlib.import_module("app.llm_report")
            payload = legacy_llm.generate_report_ai(report, emr)
            elapsed = time.time() - t0
            result = payload if isinstance(payload, dict) else {}
            keys = list(result.keys()) if result else []
            logger.info("[步骤4-AI] AI报告生成完成 model=%s keys=%s 耗时=%.2fs", self.llm_model, keys, elapsed)
            return result
        except Exception as exc:
            logger.exception("[步骤4-AI] AI报告生成失败 model=%s error=%s", self.llm_model, exc)
            raise LLMError(f"LLM report generation failed: {exc}") from exc


__all__ = ["AIService"]
