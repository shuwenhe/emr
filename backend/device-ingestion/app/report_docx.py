from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from docx import Document
from docx.shared import Inches

from .config import REPORTS_DIR


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("_", "-", "·"))


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def generate_docx_report(report: Dict[str, Any], emr: Dict[str, Any]) -> Path:
    patient = (report.get("patient") or emr.get("patient") or {})
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}

    created_at = report.get("created_at") or emr.get("created_at")
    created_dt = _parse_datetime(created_at)
    date_dir = REPORTS_DIR / created_dt.strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    patient_name = _safe_name(str(patient.get("name") or "患者")) or "患者"
    emr_id = str(emr.get("emr_id") or report.get("report_id") or "")
    emr_suffix = f"_{_safe_name(emr_id)}" if emr_id else ""
    filename = f"{patient_name}_{created_dt.strftime('%Y%m%d_%H%M%S')}{emr_suffix}.docx"
    output_path = date_dir / filename

    doc = Document()
    doc.add_heading("红外热成像评估报告", level=1)

    doc.add_paragraph(f"报告ID: {report.get('report_id', '-')}")
    doc.add_paragraph(f"采集时间: {created_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    doc.add_heading("患者信息", level=2)
    doc.add_paragraph(f"姓名: {patient.get('name', '-')}")
    
    # 性别转换为中文
    gender = patient.get('gender', '-')
    if gender in ['male', 'Male', 'MALE', 'm', 'M']:
        gender = '男'
    elif gender in ['female', 'Female', 'FEMALE', 'f', 'F']:
        gender = '女'
    
    doc.add_paragraph(f"性别: {gender}  年龄: {patient.get('age', '-')}")
    doc.add_paragraph(f"采集部位: {patient.get('body_part', '-')}")

    doc.add_heading("温度指标", level=2)
    doc.add_paragraph(f"最低温度: {metrics.get('min_c', '-')}°C")
    doc.add_paragraph(f"最高温度: {metrics.get('max_c', '-')}°C")
    doc.add_paragraph(f"平均温度: {metrics.get('avg_c', '-')}°C")

    doc.add_heading("风险等级", level=2)
    doc.add_paragraph(str(analysis.get("risk_level", "-")).upper())

    doc.add_heading("诊断结论", level=2)
    doc.add_paragraph(str(report.get("diagnosis") or "-"))

    doc.add_heading("医生意见", level=2)
    doc.add_paragraph(str(report.get("doctor_opinion") or "-"))

    image_path = report.get("thermal_marked_image")
    if image_path:
        image_file = Path(image_path)
        if image_file.exists():
            doc.add_heading("热成像图", level=2)
            doc.add_picture(str(image_file), width=Inches(5.5))

    doc.save(str(output_path))
    print(f"[DOCX] Saved report to: {output_path}")
    return output_path