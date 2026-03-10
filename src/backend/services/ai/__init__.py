"""
AI-powered services including LLM report generation and RAG.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.backend.core.config import settings
from src.backend.core.exceptions import LLMError
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


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
        
        logger.info(f"Generating AI report summary using {self.llm_model}")
        
        # TODO: Migrate from device-ingestion/app/llm_report.py
        
        raise NotImplementedError("AI service not yet implemented")


__all__ = ["AIService"]
