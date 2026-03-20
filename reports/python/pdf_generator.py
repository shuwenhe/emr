from __future__ import annotations

import ast
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Add ingestion to path for config imports
_DEVICE_INGESTION_DIR = Path(__file__).resolve().parents[2] / "ingestion"
if str(_DEVICE_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_DEVICE_INGESTION_DIR))

from app.config import DATA_DIR, REPORTS_DIR
from reports.python.thermal_label_renderer import render_labeled_thermal_image

logger = logging.getLogger(__name__)

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_FONT_NAME: Optional[str] = None

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
]

_CJK_FONT_FILES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
]


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("_", "-", "·"))


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def _text(value: Any, default: str = "-") -> str:
    raw = str(value or "").strip()
    return raw or default


def _gender_cn(value: Optional[str]) -> str:
    if not value:
        return "-"
    if value in {"male", "Male", "MALE", "m", "M", "男"}:
        return "男"
    if value in {"female", "Female", "FEMALE", "f", "F", "女"}:
        return "女"
    return str(value)


def _fmt_temp(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def _risk_level_cn(value: Any) -> str:
    level = str(value or "").strip().lower()
    if level == "high":
        return "高风险"
    if level == "medium":
        return "中风险"
    if level == "low":
        return "低风险"
    return "未知"


def _risk_score(value: Any) -> int:
    level = str(value or "").strip().lower()
    if level == "high":
        return 75
    if level == "medium":
        return 50
    if level == "low":
        return 25
    return 0


def _resolve_image_path(value: Any) -> Optional[Path]:
    raw = str(value or "").strip()
    if not raw:
        return None

    path = Path(raw)
    if path.exists() and path.is_file():
        return path

    if not path.is_absolute():
        candidate = DATA_DIR / raw.lstrip("/")
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _select_report_base_image(report: Dict[str, Any]) -> Optional[Path]:
    primary = _resolve_image_path(report.get("thermal_marked_image"))
    if primary is not None:
        return primary

    thermal_images = report.get("thermal_images") or []
    for item in thermal_images:
        if "thermal_roi_labeled" in str(item or ""):
            continue
        candidate = _resolve_image_path(item)
        if candidate is not None:
            return candidate

    return _resolve_image_path(report.get("thermal_roi_labeled_image"))


def _section_name(name: str) -> str:
    text = str(name or "")
    if any(key in text for key in ("额", "眼", "鼻", "口", "脸", "颊", "头")):
        return "头面部"
    if any(key in text for key in ("颈", "肩")):
        return "颈肩部"
    if any(key in text for key in ("背", "脊")):
        return "脊柱背部"
    if any(key in text for key in ("胸", "腹", "腰", "肾", "臀")):
        return "胸腹部"
    if any(key in text for key in ("臂", "腿", "手", "肘")):
        return "四肢部"
    return "综合评估"


def _severity_from_value(value: Any) -> str:
    try:
        number = abs(float(value))
    except Exception:
        return "轻"
    if number >= 1.5:
        return "重"
    if number >= 0.8:
        return "中"
    return "轻"


_ADVICE_NUM_RE = re.compile(r"^\s*(?:\d+[.、。)）]\s*)+")
_ADVICE_REF_RE = re.compile(r"\[(?:\s*\d+\s*(?:,\s*\d+\s*)*)\]")
_ADVICE_NOISE_RE = re.compile(r"\[\s*['\"]?\s*['\"]?(?:\s*,\s*['\"]?\s*['\"]?)*\s*\]")


def _strip_advice_num(line: str) -> str:
    """Remove leading numbering like '1.', '1、', '1. 1.' etc."""
    return _ADVICE_NUM_RE.sub("", line).strip()


def _clean_advice_text(line: str) -> str:
    """Remove references/noise in advice text, e.g. [8], [9], ['','']."""
    text = str(line or "")
    text = _ADVICE_REF_RE.sub("", text)
    text = _ADVICE_NOISE_RE.sub("", text)
    # Normalize extra spaces left after marker removal.
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _expand_advice_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        lines: List[str] = []
        for item in value:
            lines.extend(_expand_advice_value(item))
        return lines

    text = str(value or "").strip()
    if not text:
        return []

    if text[:1] in "[(" and text[-1:] in "])":
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            parsed = None
        if isinstance(parsed, (list, tuple)):
            return _expand_advice_value(parsed)

    return [text]


def _split_advice_lines(*values: Any) -> List[str]:
    lines: List[str] = []
    for value in values:
        for text in _expand_advice_value(value):
            raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
            if len(raw_lines) <= 1:
                normalized = text.replace("；", "。")
                raw_lines = [p.strip() for p in normalized.split("。") if p.strip()]
            for item in raw_lines:
                cleaned = _clean_advice_text(_strip_advice_num(item))
                if cleaned:
                    lines.append(cleaned)
    return lines


def _ensure_font() -> str:
    global _FONT_NAME
    if _FONT_NAME is not None:
        return _FONT_NAME

    for font_path in _CJK_FONT_FILES:
        candidate = Path(font_path)
        if not candidate.exists():
            continue
        try:
            font_name = candidate.stem.replace("-", "_")
            pdfmetrics.registerFont(TTFont(font_name, str(candidate)))
            _FONT_NAME = font_name
            return _FONT_NAME
        except Exception:
            continue

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _FONT_NAME = "STSong-Light"
        return _FONT_NAME
    except Exception:
        _FONT_NAME = "Helvetica"
        return _FONT_NAME


def _styles() -> Dict[str, ParagraphStyle]:
    font_name = _ensure_font()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PdfTitle",
            parent=base["Title"],
            fontName=font_name,
            fontSize=26,
            leading=32,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#003366"),
            spaceAfter=4,
            spaceBefore=6,
        ),
        "subtitle": ParagraphStyle(
            "PdfSubtitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#666666"),
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "PdfSection",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            textColor=colors.white,
            backColor=colors.HexColor("#0066cc"),
            borderPadding=(6, 10, 6, 10),
            spaceBefore=10,
            spaceAfter=8,
        ),
        "subsection": ParagraphStyle(
            "PdfSubSection",
            parent=base["Heading3"],
            fontName=font_name,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#003366"),
            spaceBefore=8,
            spaceAfter=4,
            leftIndent=2,
        ),
        "body": ParagraphStyle(
            "PdfBody",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=15,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#333333"),
        ),
        "small": ParagraphStyle(
            "PdfSmall",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8.5,
            leading=12,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#666666"),
        ),
        "center": ParagraphStyle(
            "PdfCenter",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
        ),
    }


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    cleaned = re.sub(r"</?b>", "", str(text or ""), flags=re.IGNORECASE)
    safe = (
        cleaned
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(safe, style)


def _make_image(path: Optional[Path], max_width: float, max_height: float) -> Spacer | Image:
    if path is None or not path.exists():
        return Spacer(1, 1)
    image = Image(str(path))
    try:
        width = float(image.imageWidth)
        height = float(image.imageHeight)
        scale = min(max_width / width, max_height / height)
        image.drawWidth = width * scale
        image.drawHeight = height * scale
    except Exception:
        image.drawWidth = max_width
        image.drawHeight = max_height
    return image


def _build_cover_table(patient: Dict[str, Any], created_dt: datetime, styles: Dict[str, ParagraphStyle]) -> Table:
    info = [
        ["编号", _text(patient.get("patient_id"))],
        ["姓名", _text(patient.get("name"))],
        ["性别", _gender_cn(patient.get("gender"))],
        ["年龄", _text(patient.get("age"))],
        ["日期", created_dt.strftime("%Y-%m-%d")],
    ]
    rows = [[_paragraph(a, styles["body"]), _paragraph(b, styles["body"])] for a, b in info]
    table = Table(rows, colWidths=[28 * mm, 58 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#d9e8f5")),
                ("BACKGROUND", (1, 0), (1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#0066cc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (0, -1), _ensure_font()),
                ("FONTSIZE", (0, 0), (0, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#003366")),
            ]
        )
    )
    return table


def _risk_cards(analysis: Dict[str, Any], roi_list: Sequence[Dict[str, Any]], styles: Dict[str, ParagraphStyle]) -> Table:
    section_cards = [
        ("头面部", "头面部风险"),
        ("颈肩部", "颈肩部风险"),
        ("脊柱背部", "脊柱背部风险"),
        ("胸腹部", "胸部风险"),
    ]
    cards: List[List[Any]] = []
    global_level = analysis.get("risk_level")
    for section, title in section_cards:
        matched = [item for item in roi_list if _section_name(str(item.get("name") or "")) == section]
        score = _risk_score(global_level)
        level = _risk_level_cn(global_level)
        summary = "；".join(str(item.get("name") or "") for item in matched[:2]) or "未发现明显风险"
        cards.append(
            [
                _paragraph(f"<b>{title}</b>", styles["center"]),
                _paragraph(f"<b>{score}</b>", styles["center"]),
                _paragraph(level, styles["center"]),
                _paragraph(summary, styles["small"]),
            ]
        )
    table = Table(cards, colWidths=[42 * mm, 18 * mm, 24 * mm, 78 * mm], repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#0066cc")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f0f8")),
                ("BACKGROUND", (1, 0), (2, -1), colors.HexColor("#f0f4f8")),
                ("BACKGROUND", (3, 0), (3, -1), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _image_grid(paths: Sequence[Path], width: float, height: float) -> Table:
    images = [item for item in paths[:6] if item.exists()]
    if not images:
        return Table([[Spacer(1, 1)]])

    cells: List[Any] = []
    cell_width = width / 3.0
    for path in images:
        cells.append(_make_image(path, cell_width - 8, height))
    while len(cells) % 3 != 0:
        cells.append(Spacer(1, 1))
    rows = [cells[index:index + 3] for index in range(0, len(cells), 3)]
    table = Table(rows, colWidths=[cell_width] * 3)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return table


def _rows_to_table(headers: Sequence[str], rows: Sequence[Sequence[Any]], col_widths: Sequence[float], styles: Dict[str, ParagraphStyle]) -> Table:
    header_row = [_paragraph(f"<b>{header}</b>", styles["body"]) for header in headers]
    body_rows = [[_paragraph(_text(cell), styles["small"]) for cell in row] for row in rows]
    table = Table([header_row, *body_rows], colWidths=list(col_widths), repeatRows=1)
    
    # Build style commands with alternating row colors
    style_cmds: List[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0066cc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), _ensure_font()),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#0066cc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    
    # Add alternating row background colors
    for i in range(1, len(body_rows) + 1):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f8fc")))
        else:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.white))
    
    table.setStyle(TableStyle(style_cmds))
    return table


def _header_footer(patient: Dict[str, Any], header_dt: datetime, unit_name: str):
    font_name = _ensure_font()
    patient_name = _text(patient.get("name"))
    gender = _gender_cn(patient.get("gender"))
    age = _text(patient.get("age"))
    created_text = header_dt.strftime("%Y-%m-%d %H:%M:%S")

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(20 * mm, _PAGE_HEIGHT - 14 * mm, f"{patient_name}    {gender}    {age}    {created_text}")
        canvas.drawRightString(_PAGE_WIDTH - 20 * mm, _PAGE_HEIGHT - 14 * mm, unit_name)
        canvas.setStrokeColor(colors.HexColor("#0066cc"))
        canvas.setLineWidth(0.8)
        canvas.line(18 * mm, _PAGE_HEIGHT - 16 * mm, _PAGE_WIDTH - 18 * mm, _PAGE_HEIGHT - 16 * mm)
        canvas.line(18 * mm, 13 * mm, _PAGE_WIDTH - 18 * mm, 13 * mm)
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.drawCentredString(_PAGE_WIDTH / 2.0, 7 * mm, f"- 第 {doc.page} 页 -")
        canvas.restoreState()

    return draw


def _build_summary_rows(abnormal_regions: Sequence[Dict[str, Any]]) -> List[Sequence[Any]]:
    rows: List[Sequence[Any]] = []
    for item in abnormal_regions:
        region_name = _text(item.get("region_cn") or item.get("region"))
        status = "异常高温" if str(item.get("status") or "").lower() == "high" else "异常低温"
        rows.append([region_name, status, _fmt_temp(item.get("avg_c")), _fmt_temp(item.get("delta_c"))])
    return rows or [["未发现明显异常部位", "-", "-", "-"]]


def _build_objective_rows(roi_list: Sequence[Dict[str, Any]]) -> List[Sequence[Any]]:
    rows: List[Sequence[Any]] = []
    for item in roi_list:
        rows.append(
            [
                _section_name(_text(item.get("name"), "")),
                _text(item.get("name")),
                _fmt_temp(item.get("mean_c")),
                _fmt_temp(item.get("min_c")),
                _fmt_temp(item.get("max_c")),
            ]
        )
    return rows or [["-", "-", "-", "-", "-"]]


def _group_section_rows(roi_list: Sequence[Dict[str, Any]]) -> Dict[str, List[Sequence[Any]]]:
    grouped: Dict[str, List[Sequence[Any]]] = {}
    for item in roi_list:
        roi_name = _text(item.get("name"), "")
        if not roi_name:
            continue
        section = _section_name(roi_name)
        grouped.setdefault(section, []).append(
            [
                roi_name,
                f"{roi_name}温度分布见热区变化",
                _severity_from_value(item.get("std_c")),
                _text(item.get("count")),
                _fmt_temp(item.get("mean_c")),
                _fmt_temp(item.get("std_c")),
            ]
        )
    return grouped


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
        plan.get("treatment_plan_text") if isinstance(plan, dict) else None,
        plan.get("ai_recommendation") if isinstance(plan, dict) else None,
        ai_payload.get("report_note") if isinstance(ai_payload, dict) else None,
    ) or ["以上为热图所提示可能性，请结合临床进一步诊查。"]


def _collect_evidence_ids(report: Dict[str, Any], emr: Dict[str, Any]) -> List[str]:
    collected: List[str] = []

    def _add(values: Any) -> None:
        if isinstance(values, (list, tuple)):
            for item in values:
                text = str(item or "").strip()
                if text:
                    collected.append(text)

    for container in (report, emr):
        if not isinstance(container, dict):
            continue
        _add(container.get("plan_evidence_item_ids"))
        _add(container.get("health_advice_evidence_item_ids"))
        _add(container.get("diagnosis_evidence_item_ids"))
        _add(container.get("evidence_item_ids"))

        report_payload = container.get("report")
        if isinstance(report_payload, dict):
            _add(report_payload.get("plan_evidence_item_ids"))
            _add(report_payload.get("health_advice_evidence_item_ids"))
            _add(report_payload.get("diagnosis_evidence_item_ids"))
            _add(report_payload.get("evidence_item_ids"))

    # Preserve order while deduplicating.
    seen = set()
    ordered: List[str] = []
    for item in collected:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def generate_pdf_report(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    *,
    generated_at: Optional[datetime] = None,
) -> Path:
    styles = _styles()
    created_at = report.get("created_at") or emr.get("created_at")
    created_dt = _parse_datetime(created_at)
    report_generated_dt = generated_at or datetime.now()
    patient = report.get("patient") or emr.get("patient") or {}
    patient_name = _safe_name(str(patient.get("name") or "患者")) or "患者"
    date_dir = REPORTS_DIR / report_generated_dt.strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    output_path = date_dir / f"{patient_name}{report_generated_dt.strftime('%Y%m%d%H%M%S')}.pdf"

    analysis = report.get("analysis") if isinstance(report, dict) else {}
    if not isinstance(analysis, dict):
        analysis = {}
    metrics = analysis.get("temperature_metrics") if isinstance(analysis, dict) else {}
    if not isinstance(metrics, dict):
        metrics = {}
    roi_analysis = analysis.get("roi_analysis") if isinstance(analysis, dict) else {}
    roi_list = roi_analysis.get("roi_list") if isinstance(roi_analysis, dict) else []
    if not isinstance(roi_list, list):
        roi_list = []
    regional = analysis.get("regional_comparison") if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else []
    if not isinstance(abnormal_regions, list):
        abnormal_regions = []

    # RAG/LLM generated text fields
    ai_payload = report.get("ai") or {}
    diagnosis_text = _text(report.get("diagnosis") or emr.get("diagnosis"))
    doctor_opinion_text = _text(
        report.get("doctor_opinion")
        or emr.get("doctor_opinion")
        or (ai_payload.get("doctor_opinion") if isinstance(ai_payload, dict) else None)
    )
    report_note_text = _text(
        (ai_payload.get("report_note") if isinstance(ai_payload, dict) else None)
        or (report.get("treatment_plan") or {}).get("ai_recommendation")
    )
    summary_text = _text(analysis.get("summary") or diagnosis_text)
    key_findings: List[str] = []
    if isinstance(analysis.get("key_findings"), list):
        key_findings = [str(f) for f in analysis["key_findings"] if f]

    unit_name = _text(emr.get("hospital") or emr.get("unit") or "张氏疼痛外治中心")
    system_name = "红外影像云平台-红外影像热层析系统"

    # Build labeled thermal image (re-rendered from base image + ROI data)
    image_candidates: List[Path] = []
    base_image = _select_report_base_image(report)
    labeled_image = render_labeled_thermal_image(base_image, report, "pdf_labeled") if base_image is not None else None
    primary_image = labeled_image or base_image
    if primary_image is not None:
        image_candidates.append(primary_image)
    for item in report.get("thermal_images") or []:
        candidate = _resolve_image_path(item)
        if candidate is not None and candidate not in image_candidates:
            image_candidates.append(candidate)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title="红外热成像评估报告",
        author=unit_name,
    )

    story: List[Any] = []

    # ── 封面 ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 18 * mm))
    story.append(_paragraph("红外热成像评估报告", styles["title"]))
    story.append(_paragraph("INFRARED THERMAL IMAGING HEALTH REPORT", styles["subtitle"]))
    story.append(Spacer(1, 8 * mm))
    story.append(_paragraph("个人信息", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_build_cover_table(patient, report_generated_dt, styles))
    story.append(Spacer(1, 10 * mm))
    if primary_image is not None:
        story.append(_make_image(primary_image, 130 * mm, 100 * mm))
        story.append(Spacer(1, 6 * mm))
    story.append(_paragraph(unit_name, styles["center"]))
    story.append(_paragraph(system_name, styles["subtitle"]))
    story.append(PageBreak())

    # ── 一、温度指标概览 ───────────────────────────────────────────────────────
    story.append(_paragraph("一、温度指标概览", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_paragraph("提示", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        _paragraph(
            "红外热成像技术是一种功能影像学技术，它被动接受人体红外热信号，"
            "对人体绝无任何辐射及伤害，孕妇、哺乳期妇女、儿童、老人均可进行检查。",
            styles["small"],
        )
    )
    story.append(Spacer(1, 1 * mm))
    story.append(
        _paragraph(
            "本报告利用红外热成像技术检测各部位温度变化，并对此进行健康评估，"
            "旨在帮您了解自身健康、亚健康状况，作为疾病诊断、治疗的参考依据。",
            styles["small"],
        )
    )
    story.append(Spacer(1, 1 * mm))
    story.append(
        _paragraph(
            "若您存在脏器的切除史，报告中提示了该脏器风险，代表该脏器周围组织存在异常。",
            styles["small"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    # 整体热图（全部图片缩略网格）
    if image_candidates:
        story.append(_image_grid(image_candidates, 170 * mm, 52 * mm))
        story.append(Spacer(1, 5 * mm))
    # 温度指标表
    story.append(_paragraph("整体温度指标", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        _rows_to_table(
            ["最低温度 (°C)", "最高温度 (°C)", "平均温度 (°C)", "风险等级"],
            [[
                _fmt_temp(metrics.get("min_c")),
                _fmt_temp(metrics.get("max_c")),
                _fmt_temp(metrics.get("avg_c")),
                _risk_level_cn(analysis.get("risk_level")),
            ]],
            [40 * mm, 40 * mm, 40 * mm, 40 * mm],
            styles,
        )
    )
    story.append(Spacer(1, 6 * mm))
    # 风险概览
    story.append(_paragraph("风险概览", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_risk_cards(analysis, roi_list, styles))
    story.append(PageBreak())

    # ── 二、热成像图（含叠加人体部位温度标签） ────────────────────────────────
    story.append(_paragraph("二、热成像图（含人体姿态分区温度标签）", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    if primary_image is not None:
        story.append(_make_image(primary_image, 155 * mm, 118 * mm))
        story.append(Spacer(1, 4 * mm))
        story.append(_paragraph("※ 图中标签显示各部位均温（°C）", styles["small"]))
    else:
        story.append(_paragraph("热成像图文件未找到", styles["body"]))
    story.append(PageBreak())

    # ── 三、姿态分区温度（ROI）详情 ───────────────────────────────────────────
    story.append(_paragraph("三、姿态分区温度（ROI）详情", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_paragraph("各部位温度统计", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    # 完整 ROI 表：分组 / 部位 / 均温 / 最低 / 最高 / 标准差
    roi_full_rows: List[Sequence[Any]] = []
    for item in roi_list:
        roi_full_rows.append([
            _section_name(_text(item.get("name"), "")),
            _text(item.get("name")),
            _fmt_temp(item.get("mean_c")),
            _fmt_temp(item.get("min_c")),
            _fmt_temp(item.get("max_c")),
            _fmt_temp(item.get("std_c")),
        ])
    if roi_full_rows:
        story.append(
            _rows_to_table(
                ["分组", "部位", "均温°C", "最低°C", "最高°C", "标准差"],
                roi_full_rows,
                [28 * mm, 32 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm],
                styles,
            )
        )
    else:
        story.append(_paragraph("暂无 ROI 分区数据", styles["body"]))
    story.append(PageBreak())

    # ── 四、异常区域 ──────────────────────────────────────────────────────────
    story.append(_paragraph("四、异常区域", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    if primary_image is not None:
        story.append(_make_image(primary_image, 150 * mm, 100 * mm))
        story.append(Spacer(1, 5 * mm))
    story.append(_paragraph("异常区域汇总", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        _rows_to_table(
            ["部位", "异常类型", "均温°C", "温差°C"],
            _build_summary_rows(abnormal_regions),
            [58 * mm, 34 * mm, 28 * mm, 28 * mm],
            styles,
        )
    )
    story.append(PageBreak())

    # ── 五、诊断结论 ──────────────────────────────────────────────────────────
    story.append(_paragraph("五、诊断结论", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_paragraph(summary_text, styles["body"]))
    if key_findings:
        story.append(Spacer(1, 5 * mm))
        story.append(_paragraph("主要发现", styles["subsection"]))
        story.append(Spacer(1, 2 * mm))
        for finding in key_findings:
            story.append(_paragraph(f"· {finding}", styles["body"]))
            story.append(Spacer(1, 1 * mm))
    story.append(PageBreak())

    # ── 六、医生意见 ──────────────────────────────────────────────────────────
    story.append(_paragraph("六、医生意见", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_paragraph(doctor_opinion_text if doctor_opinion_text != "-" else "暂无医生意见", styles["body"]))
    if report_note_text and report_note_text != "-":
        story.append(Spacer(1, 5 * mm))
        story.append(_paragraph("报告说明", styles["subsection"]))
        story.append(Spacer(1, 2 * mm))
        story.append(_paragraph(report_note_text, styles["body"]))
    story.append(PageBreak())

    # ── 七、保健建议 ──────────────────────────────────────────────────────────
    story.append(_paragraph("七、保健建议", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    advice_lines = _advice_rows(report, emr)
    evidence_ids = _collect_evidence_ids(report, emr)
    evidence_suffix = f" [{','.join(evidence_ids)}]" if evidence_ids else " [NO_EVIDENCE_ID]"
    for index, line in enumerate(advice_lines, start=1):
        story.append(_paragraph(f"{index}、{line}", styles["body"]))
        logger.info("[PDF-ADVICE] %s、%s%s", index, line, evidence_suffix)
        story.append(Spacer(1, 2 * mm))  # number is added here; _split_advice_lines strips any pre-existing numbering
    story.append(Spacer(1, 8 * mm))
    story.append(_paragraph(f"评估日期：{report_generated_dt.strftime('%Y-%m-%d')}", styles["small"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_paragraph("以上为热图所提示可能性，请结合临床进一步诊查。", styles["small"]))

    header_footer = _header_footer(patient, report_generated_dt, unit_name)
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return output_path
