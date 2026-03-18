from __future__ import annotations

import os
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


def _split_advice_lines(*values: Any) -> List[str]:
    lines: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = text.replace("；", "。")
        for piece in normalized.split("。"):
            item = piece.strip()
            if item:
                lines.append(item)
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
    safe = (
        str(text or "")
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
    sections = ["头面部", "颈肩部", "脊柱背部"]
    cards: List[List[Any]] = []
    global_level = analysis.get("risk_level")
    for section in sections:
        matched = [item for item in roi_list if _section_name(str(item.get("name") or "")) == section]
        score = _risk_score(global_level)
        level = _risk_level_cn(global_level)
        summary = "；".join(str(item.get("name") or "") for item in matched[:2]) or "未发现明显风险"
        cards.append(
            [
                _paragraph(f"<b>{section}风险</b>", styles["center"]),
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


def _header_footer(patient: Dict[str, Any], created_dt: datetime, unit_name: str):
    font_name = _ensure_font()
    patient_name = _text(patient.get("name"))
    gender = _gender_cn(patient.get("gender"))
    age = _text(patient.get("age"))
    created_text = created_dt.strftime("%Y-%m-%d %H:%M:%S")

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
    return _split_advice_lines(
        report.get("doctor_opinion"),
        plan.get("ai_recommendation") if isinstance(plan, dict) else None,
        ai_payload.get("report_note") if isinstance(ai_payload, dict) else None,
    ) or ["以上为热图所提示可能性，请结合临床进一步诊查。"]


def generate_pdf_report(report: Dict[str, Any], emr: Dict[str, Any]) -> Path:
    styles = _styles()
    created_at = report.get("created_at") or emr.get("created_at")
    created_dt = _parse_datetime(created_at)
    # Keep capture time for content display, but use generation time for output
    # filename/path to avoid reusing stale historical report files.
    report_generated_dt = datetime.now()
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

    unit_name = _text(emr.get("hospital") or emr.get("unit") or "张氏疼痛外治中心")
    system_name = "红外影像云平台-红外影像热层析系统"

    image_candidates: List[Path] = []
    base_image = _select_report_base_image(report)
    primary_image = render_labeled_thermal_image(base_image, report, "pdf_labeled") if base_image is not None else None
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

    # Cover page
    story.append(Spacer(1, 18 * mm))
    story.append(_paragraph("红外热成像评估报告", styles["title"]))
    story.append(_paragraph("INFRARED THERMAL IMAGING HEALTH REPORT", styles["subtitle"]))
    story.append(Spacer(1, 8 * mm))
    story.append(_paragraph("个人信息", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_build_cover_table(patient, created_dt, styles))
    story.append(Spacer(1, 20 * mm))
    if primary_image is not None:
        story.append(_make_image(primary_image, 120 * mm, 90 * mm))
        story.append(Spacer(1, 8 * mm))
    story.append(_paragraph(unit_name, styles["center"]))
    story.append(_paragraph(system_name, styles["subtitle"]))
    story.append(PageBreak())

    # Overview page
    story.append(_paragraph("机体功能状态实时热像", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_image_grid(image_candidates or ([primary_image] if primary_image else []), 170 * mm, 48 * mm))
    story.append(Spacer(1, 6 * mm))
    summary_table = _rows_to_table(
        ["最低温度", "最高温度", "平均温度", "风险等级"],
        [[_fmt_temp(metrics.get("min_c")), _fmt_temp(metrics.get("max_c")), _fmt_temp(metrics.get("avg_c")), _risk_level_cn(analysis.get("risk_level"))]],
        [35 * mm, 35 * mm, 35 * mm, 35 * mm],
        styles,
    )
    story.append(summary_table)
    story.append(Spacer(1, 7 * mm))
    story.append(_paragraph("风险概览", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_risk_cards(analysis, roi_list, styles))
    story.append(Spacer(1, 7 * mm))
    story.append(_paragraph("热图所见", styles["subsection"]))
    story.append(Spacer(1, 1 * mm))
    story.append(_paragraph(_text(analysis.get("summary") or report.get("diagnosis") or "未见明显异常描述"), styles["body"]))
    story.append(PageBreak())

    # Abnormal regions and objective data
    story.append(_paragraph("代谢异常部位热图", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    if primary_image is not None:
        story.append(_make_image(primary_image, 150 * mm, 90 * mm))
        story.append(Spacer(1, 6 * mm))
    story.append(_paragraph("异常区域汇总", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        _rows_to_table(
            ["部位", "异常类型", "均温℃", "温差℃"],
            _build_summary_rows(abnormal_regions),
            [58 * mm, 34 * mm, 28 * mm, 28 * mm],
            styles,
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(_paragraph("客观热源数据表", styles["subsection"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        _rows_to_table(
            ["分组", "部位", "温度℃", "最低℃", "最高℃"],
            _build_objective_rows(roi_list),
            [34 * mm, 46 * mm, 22 * mm, 22 * mm, 22 * mm],
            styles,
        )
    )

    # Detail pages by section
    grouped_sections = _group_section_rows(roi_list)
    for section_name, rows in grouped_sections.items():
        story.append(PageBreak())
        story.append(_paragraph(section_name, styles["section"]))
        story.append(Spacer(1, 2 * mm))
        story.append(
            _rows_to_table(
                ["项目", "热源描述", "热特征度", "面积", "均值", "标准差"],
                rows,
                [24 * mm, 72 * mm, 22 * mm, 18 * mm, 18 * mm, 18 * mm],
                styles,
            )
        )
        story.append(Spacer(1, 8 * mm))
        if primary_image is not None:
            story.append(_paragraph("图像", styles["subsection"]))
            story.append(Spacer(1, 2 * mm))
            story.append(_make_image(primary_image, 130 * mm, 90 * mm))

    # Advice page
    story.append(PageBreak())
    story.append(_paragraph("保健建议", styles["section"]))
    story.append(Spacer(1, 3 * mm))
    for index, line in enumerate(_advice_rows(report, emr), start=1):
        story.append(_paragraph(f"{index}、{line}", styles["body"]))
        story.append(Spacer(1, 2 * mm))
    story.append(Spacer(1, 8 * mm))
    story.append(_paragraph(f"评估日期：{created_dt.strftime('%Y-%m-%d')}", styles["small"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_paragraph("以上为热图所提示可能性，请结合临床进一步诊查。", styles["small"]))

    header_footer = _header_footer(patient, created_dt, unit_name)
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return output_path
