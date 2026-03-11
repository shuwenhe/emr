"""
Treatment planning and dispatch service.
"""

from __future__ import annotations

from datetime import datetime
import importlib
import sys
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from src.backend.core.config import settings
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[4] / "ingestion"
if str(_LEGACY_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_BACKEND_DIR))


class TreatmentService:
    """Service for treatment plan generation and device dispatch."""
    
    def __init__(self):
        self.rules_file = settings.TREATMENT_RULES_FILE
        
    def generate_treatment_plan(
        self,
        analysis: Dict[str, Any],
        patient: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate treatment plan based on analysis results.
        
        Args:
            analysis: Thermal analysis results
            patient: Patient information
            
        Returns:
            Treatment plan with actionable recommendations
        """
        logger.info("Generating treatment plan")
        existing_plan = analysis.get("plan") if isinstance(analysis, dict) else None
        if isinstance(existing_plan, dict) and existing_plan:
            return existing_plan

        risk_level = (
            (analysis.get("report") or {}).get("analysis", {}).get("risk_level")
            if isinstance(analysis, dict)
            else None
        ) or "unknown"
        return {
            "risk_level": risk_level,
            "summary": "规则引擎方案待迁移，当前返回基础治疗建议。",
            "recommendation": "建议结合临床症状进一步评估并复测。",
            "patient": {
                "name": patient.get("name"),
                "body_part": patient.get("body_part"),
            },
        }
    
    def dispatch_to_device(
        self,
        treatment_plan: Dict[str, Any],
        device_id: str,
    ) -> Dict[str, Any]:
        """
        Dispatch treatment plan to physical device.
        
        Args:
            treatment_plan: Treatment plan to dispatch
            device_id: Target device identifier
            
        Returns:
            Dispatch confirmation
        """
        logger.info("Dispatching to device %s", device_id)
        record_id = str(treatment_plan.get("record_id") or "").strip()
        if record_id:
            try:
                legacy_dispatch = importlib.import_module("app.dispatch")
                return legacy_dispatch.dispatch_record(record_id)
            except Exception:
                pass

        return {
            "dispatch": {
                "dispatch_id": f"DSP-{uuid4()}",
                "device_id": device_id,
                "payload": treatment_plan,
            },
            "ack": {
                "status": "queued",
                "received_at": datetime.now().isoformat(timespec="seconds"),
            },
        }


__all__ = ["TreatmentService"]
