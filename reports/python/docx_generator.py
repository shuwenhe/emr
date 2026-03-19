from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import matplotlib

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches

import sys
from pathlib import Path
# Add ingestion to path for config/llm imports
_DEVICE_INGESTION_DIR = Path(__file__).resolve().parents[2] / "ingestion"
if str(_DEVICE_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_DEVICE_INGESTION_DIR))

from app.config import DATA_DIR, REPORTS_DIR
from reports.python.thermal_label_renderer import render_labeled_thermal_image

matplotlib.use("Agg")

_CJK_FONT_CANDIDATES = [
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Heiti SC",
    "Arial Unicode MS",
]

_GRID_REGION_MAP_DEFAULT = {
    "r1_c1": "左上（左肩颈）",
    "r1_c2": "上中（颈胸）",
    "r1_c3": "右上（右肩颈）",
    "r2_c1": "左中（左胸腹）",
    "r2_c2": "中部（胸腹中线）",
    "r2_c3": "右中（右胸腹）",
    "r3_c1": "左下（左腰髋）",
    "r3_c2": "下中（下腹/骨盆）",
    "r3_c3": "右下（右腰髋）",
}

_GRID_REGION_MAP_FACE = {
    "r1_c1": "左额颞区",
    "r1_c2": "额中区",
    "r1_c3": "右额颞区",
    "r2_c1": "左眼眶/左颊上区",
    "r2_c2": "鼻-口周中区",
    "r2_c3": "右眼眶/右颊上区",
    "r3_c1": "左颊下颌区",
    "r3_c2": "颏下区",
    "r3_c3": "右颊下颌区",
}

_GRID_REGION_MAP_BACK = {
    "r1_c1": "左上背（肩胛上区）",
    "r1_c2": "上背中线区",
    "r1_c3": "右上背（肩胛上区）",
    "r2_c1": "左中背（肩胛内侧）",
    "r2_c2": "中背脊柱旁区",
    "r2_c3": "右中背（肩胛内侧）",
    "r3_c1": "左下背（腰背）",
    "r3_c2": "下背中线（腰骶）",
    "r3_c3": "右下背（腰背）",
}

_EXCLUDED_REPORT_REGIONS = {"r1_c1", "r1_c2", "r1_c3", "r2_c1"}


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("_", "-", "·"))


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def _strip_think(text: str) -> str:
    if not text:
        return text
    return text.replace("<think>", "").replace("</think>", "").strip()


def _fmt_temp(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def _text(value: Any, default: str = "-") -> str:
    raw = str(value or "").strip()
    return raw or default


def _risk_level_cn(value: Any) -> str:
    level = str(value or "").strip().lower()
    if level == "high":
        return "高风险"
    if level == "medium":
        return "中风险"
    if level == "low":
        return "低风险"
    return "未知"



_ADVICE_NUM_RE = re.compile(r"^\s*(?:\d+[.、。)）]\s*)+")


def _strip_advice_num(line: str) -> str:
    """Remove leading numbering like '1.', '1、', '1. 1.' etc."""
    return _ADVICE_NUM_RE.sub("", line).strip()


def _split_advice_lines(*values: Any) -> List[str]:
    lines: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        # Prefer newline-split (LLM outputs numbered lists with \n).
        # Fall back to '。'-split for plain prose.
        raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(raw_lines) <= 1:
            normalized = text.replace("；", "。")
            raw_lines = [p.strip() for p in normalized.split("。") if p.strip()]
        for item in raw_lines:
            cleaned = _strip_advice_num(item)
            if cleaned:
                lines.append(cleaned)
    return lines


def _advice_rows(report: Dict[str, Any], emr: Dict[str, Any]) -> List[str]:
    plan = report.get("treatment_plan") or emr.get("treatment_plan") or {}
    ai_payload = report.get("ai") or {}
    health_advice = (
        report.get("health_advice")
        or emr.get("health_advice")
        or (plan.get("health_advice") if isinstance(plan, dict) else None)
        or (ai_payload.get("health_advice") if isinstance(ai_payload, dict) else None)
    )
    return _split_advice_lines(
        health_advice,
        report.get("doctor_opinion"),
        plan.get("ai_recommendation") if isinstance(plan, dict) else None,
        ai_payload.get("report_note") if isinstance(ai_payload, dict) else None,
    ) or ["以上为热图所提示可能性，请结合临床进一步诊查。"]


def _build_summary_rows(abnormal_regions: Sequence[Dict[str, Any]]) -> List[str]:
    rows: List[str] = []
    for item in abnormal_regions:
        region_name = _text(item.get("region_cn") or item.get("region"))
        status = "异常高温" if str(item.get("status") or "").lower() == "high" else "异常低温"
        rows.append(
            f"{region_name}：{status}，均温 {_fmt_temp(item.get('avg_c'))}°C，Δ {_fmt_temp(item.get('delta_c'))}°C"
        )
    return rows


def _build_objective_rows(roi_list: Sequence[Dict[str, Any]]) -> List[str]:
    rows: List[str] = []
    for item in roi_list:
        rows.append(
            f"{_region_to_body_part_cn(_text(item.get('name'), ''), None) or _text(item.get('name'))}："
            f"均温 {_fmt_temp(item.get('mean_c'))}°C，最低 {_fmt_temp(item.get('min_c'))}°C，最高 {_fmt_temp(item.get('max_c'))}°C"
        )
    return rows


def _region_to_body_part_cn(region_code: str, body_part: Optional[str]) -> str:
    code = str(region_code or "").strip().lower()
    body = str(body_part or "").strip().lower()
    if not code:
        return ""

    face_keys = ("面", "脸", "颜面", "头面", "face")
    back_keys = ("背", "腰背", "肩背", "背部", "back")
    if any(key in body for key in face_keys):
        region_map = _GRID_REGION_MAP_FACE
    elif any(key in body for key in back_keys):
        region_map = _GRID_REGION_MAP_BACK
    else:
        region_map = _GRID_REGION_MAP_DEFAULT
    return region_map.get(code, code)


def _resolve_image_file(image_path: str) -> Optional[Path]:
    raw = str(image_path or "").strip()
    if not raw:
        return None

    candidate = Path(raw)
    if candidate.exists() and candidate.is_file():
        return candidate

    normalized = raw.lstrip("/")
    if normalized.startswith("data/"):
        normalized = normalized[5:]
    candidate = DATA_DIR / normalized
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _resolve_rag_source_file(source_path: str) -> Optional[Path]:
    raw = str(source_path or "").strip()
    if not raw or raw == "-":
        return None

    normalized_raw = raw
    for prefix in ("来源：", "来源:", "source:", "Source:"):
        if normalized_raw.startswith(prefix):
            normalized_raw = normalized_raw[len(prefix):].strip()
            break

    match = re.search(r"([A-Za-z0-9_./\\-]+\.(?:docx?|DOCX?))", normalized_raw)
    if match:
        normalized_raw = match.group(1)

    normalized_raw = normalized_raw.replace("\\", "/").strip().lstrip("./")

    path = Path(normalized_raw)
    candidates: list[Path] = []
    project_root = Path(__file__).resolve().parents[2]

    # Explicit mapping for RAG corpus relative source paths.
    # Example: tcm/tcm_part_001460.docx -> emr/rag/dataset/tcm/tcm_part_001460.docx
    if normalized_raw.startswith("tcm/"):
        candidates.append(project_root / "rag" / "dataset" / normalized_raw)

    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(project_root / path)

        env_source_root = os.getenv("RAG_SOURCE_ROOT", "").strip()
        if env_source_root:
            candidates.append(Path(env_source_root) / path)

        env_kb_source_dir = os.getenv("KB_SOURCE_DIR", "").strip()
        if env_kb_source_dir:
            candidates.append(Path(env_kb_source_dir) / path)

        candidates.append(project_root / "rag" / "dataset" / path)

        # Common TCM shape: source="tcm/xxx.docx" maps to rag/dataset/tcm/xxx.docx.
        if normalized_raw.startswith("tcm/"):
            candidates.append(project_root / "rag" / "dataset" / normalized_raw)

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        except Exception:
            continue

    # Best-effort fallback: still return an absolute candidate so the docx keeps
    # a clickable file hyperlink instead of plain text.
    for candidate in candidates:
        try:
            if candidate.is_absolute():
                return candidate
        except Exception:
            continue
    return None


def _add_external_hyperlink(paragraph, text: str, target_uri: str) -> None:
    if not text or not target_uri:
        return

    rel_id = paragraph.part.relate_to(target_uri, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)

    run = OxmlElement("w:r")
    run_props = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    run_props.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_props.append(underline)

    run.append(run_props)
    text_elem = OxmlElement("w:t")
    text_elem.text = text
    run.append(text_elem)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _append_source_file_link(paragraph, source: str) -> bool:
    source_file = _resolve_rag_source_file(source)
    if source_file is None:
        return False

    label_source = str(source or "").strip()
    if not label_source:
        label_source = source_file.name
    paragraph.add_run("，")

    link_mode = os.getenv("DOCX_SOURCE_LINK_MODE", "path").strip().lower()
    if link_mode == "uri":
        target = source_file.as_uri()
    else:
        # Better compatibility for Linux/WPS: use plain absolute path by default.
        target = str(source_file)

    try:
        _add_external_hyperlink(paragraph, f"来源：{label_source}", target)
    except ValueError:
        # Fallback for paths that cannot be represented as URI in rare cases.
        _add_external_hyperlink(paragraph, f"来源：{label_source}", str(source_file))
    return True


def generate_docx_report(report: Dict[str, Any], emr: Dict[str, Any]) -> Path:
    patient = (report.get("patient") or emr.get("patient") or {})
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}
    regional = (analysis.get("regional_comparison") or {}) if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else []
    if not isinstance(abnormal_regions, list):
        abnormal_regions = []

    # 使用当前时间作为报告生成时间（而不是采集时间）
    report_generated_dt = datetime.now()
    date_dir = REPORTS_DIR / report_generated_dt.strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    patient_name = _safe_name(str(patient.get("name") or "患者")) or "患者"
    filename = f"{patient_name}{report_generated_dt.strftime('%Y%m%d%H%M%S')}.docx"
    output_path = date_dir / filename
    
    # 解析采集时间用于报告内容显示
    created_at = report.get("created_at") or emr.get("created_at")
    created_dt = _parse_datetime(created_at)

    doc = Document()
    doc.add_heading("红外热成像评估报告", level=1)
    doc.add_paragraph(_text(emr.get("hospital") or emr.get("unit") or "张氏疼痛外治中心"))
    doc.add_paragraph("红外影像云平台-红外影像热层析系统")

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
    doc.add_paragraph(f"最低温度: {_fmt_temp(metrics.get('min_c'))}°C")
    doc.add_paragraph(f"最高温度: {_fmt_temp(metrics.get('max_c'))}°C")
    doc.add_paragraph(f"平均温度: {_fmt_temp(metrics.get('avg_c'))}°C")
    doc.add_paragraph(f"样本数量: {metrics.get('count', '-')}")

    # 添加姿态分区温度（ROI）信息
    roi_analysis = analysis.get("roi_analysis") or {}
    doc.add_heading("姿态分区温度（ROI）", level=2)
    if roi_analysis and roi_analysis.get("roi_list"):
        roi_list = roi_analysis.get("roi_list", [])
        doc.add_paragraph(f"检测到: {len(roi_list)} 个身体部位")

        for roi in roi_list:
            doc.add_paragraph(
                f"{roi.get('name', '-')}: 平均{_fmt_temp(roi.get('mean_c'))}°C，"
                f"范围{_fmt_temp(roi.get('min_c'))}-{_fmt_temp(roi.get('max_c'))}°C，"
                f"样本{roi.get('count', '-')}",
                style="List Bullet"
            )
    else:
        doc.add_paragraph("未检测到有效 ROI 分区数据")

    # 异常区域
    doc.add_heading("异常区域", level=2)
    summary_rows = _build_summary_rows(abnormal_regions)
    if summary_rows:
        for row in summary_rows:
            doc.add_paragraph(row, style="List Bullet")
    else:
        doc.add_paragraph("未发现明显异常区域")

    doc.add_heading("风险等级", level=2)
    doc.add_paragraph(_risk_level_cn(analysis.get("risk_level")))

    doc.add_heading("热图所见", level=2)
    thermal_summary = _text(analysis.get("summary") or report.get("diagnosis") or emr.get("diagnosis"))
    doc.add_paragraph(_strip_think(thermal_summary))

    doc.add_heading("客观热源数据", level=2)
    objective_rows = _build_objective_rows(roi_analysis.get("roi_list", []) if isinstance(roi_analysis, dict) else [])
    if objective_rows:
        for row in objective_rows:
            doc.add_paragraph(row, style="List Bullet")
    else:
        doc.add_paragraph("无可用客观热源数据")

    doc.add_heading("诊断结论", level=2)
    doc.add_paragraph(_strip_think(_text(report.get("diagnosis") or emr.get("diagnosis"))))

    doc.add_heading("医生意见", level=2)
    doc.add_paragraph(_strip_think(_text(report.get("doctor_opinion"))))

    doc.add_heading("保健建议", level=2)
    for index, line in enumerate(_advice_rows(report, emr), start=1):
        doc.add_paragraph(f"{index}、{_strip_think(line)}")

    image_path = report.get("thermal_marked_image") or report.get("thermal_roi_labeled_image")
    image_file = _resolve_image_file(str(image_path or "")) if image_path else None
    if image_file is None:
        thermal_images = report.get("thermal_images") if isinstance(report, dict) else None
        if isinstance(thermal_images, list):
            for item in thermal_images:
                if "thermal_roi_labeled" in str(item or ""):
                    continue
                image_file = _resolve_image_file(str(item or ""))
                if image_file is not None:
                    break

    doc.add_heading("热成像图", level=2)
    if image_file is not None:
        labeled_image = render_labeled_thermal_image(image_file, report, "docx_labeled")
        doc.add_picture(str(labeled_image or image_file), width=Inches(5.5))
    else:
        doc.add_paragraph("热成像图文件未找到")

    doc.save(str(output_path))
    print(f"[DOCX] Saved report to: {output_path}")
    return output_path
