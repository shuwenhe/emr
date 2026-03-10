"""
AI-powered services including LLM report generation and RAG.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

from src.backend.core.config import settings
from src.backend.core.exceptions import LLMError
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend" / "device-ingestion"
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
            logger.warning("LLM features are disabled")
            return {}

        logger.info("Generating AI report summary using %s", self.llm_model)
        try:
            legacy_llm = importlib.import_module("app.llm_report")
            payload = legacy_llm.generate_report_ai(report, emr)
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            raise LLMError(f"LLM report generation failed: {exc}") from exc


__all__ = ["AIService"]
