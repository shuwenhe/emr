"""
Treatment planning and dispatch service.
"""

from __future__ import annotations

from datetime import datetime
import importlib
import sys
import time
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


_LEGACY_BACKEND_DIR = Path(__file__).resolve().parents[3] / "ingestion"
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
        patient_name = patient.get("name", "未知") if isinstance(patient, dict) else "未知"
        risk_in = (
            (analysis.get("report") or {}).get("analysis", {}).get("risk_level", "未知")
            if isinstance(analysis, dict) else "未知"
        )
        logger.info("[步骤5-治疗] 开始生成治疗方案 patient=%s risk_level=%s", patient_name, risk_in)
        existing_plan = analysis.get("plan") if isinstance(analysis, dict) else None
        if isinstance(existing_plan, dict) and existing_plan:
            logger.info("[步骤5-治疗] 使用分析中预置方案 patient=%s", patient_name)
            return existing_plan

        risk_level = (
            (analysis.get("report") or {}).get("analysis", {}).get("risk_level")
            if isinstance(analysis, dict)
            else None
        ) or "unknown"
        plan = {
            "risk_level": risk_level,
            "summary": "规则引擎方案待迁移，当前返回基础治疗建议。",
            "recommendation": "建议结合临床症状进一步评估并复测。",
            "patient": {
                "name": patient.get("name"),
                "body_part": patient.get("body_part"),
            },
        }
        logger.info("[步骤5-治疗] 治疗方案生成完成 patient=%s risk_level=%s", patient_name, risk_level)
        return plan
    
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
        record_id = str(treatment_plan.get("record_id") or "").strip()
        logger.info("[步骤6-下发] 开始下发治疗方案 device_id=%s record_id=%s", device_id, record_id)
        t0 = time.time()
        if record_id:
            try:
                legacy_dispatch = importlib.import_module("app.dispatch")
                result = legacy_dispatch.dispatch_record(record_id)
                elapsed = time.time() - t0
                logger.info("[步骤6-下发] 设备下发完成(legacy) device_id=%s record_id=%s 耗时=%.2fs", device_id, record_id, elapsed)
                return result
            except Exception:
                pass

        dispatch_id = f"DSP-{uuid4()}"
        result = {
            "dispatch": {
                "dispatch_id": dispatch_id,
                "device_id": device_id,
                "payload": treatment_plan,
            },
            "ack": {
                "status": "queued",
                "received_at": datetime.now().isoformat(timespec="seconds"),
            },
        }
        elapsed = time.time() - t0
        logger.info("[步骤6-下发] 设备下发完成 device_id=%s dispatch_id=%s status=queued 耗时=%.2fs", device_id, dispatch_id, elapsed)
        return result


__all__ = ["TreatmentService"]
