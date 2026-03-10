from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

from docx import Document
from docx.shared import Inches

import sys
from pathlib import Path

# Import from new core configuration
from src.backend.core.config import settings
from src.backend.core.logging import get_logger

# Add device-ingestion to path for temporary backward compatibility
_DEVICE_INGESTION_DIR = Path(__file__).resolve().parents[4] / "backend" / "device-ingestion"
if str(_DEVICE_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_DEVICE_INGESTION_DIR))

from app.llm_report import generate_report_ai, is_llm_enabled

matplotlib.use("Agg")

logger = get_logger(__name__)
DATA_DIR = settings.DATA_DIR
REPORTS_DIR = settings.REPORTS_DIR

THERMAL_PLOT_BOUNDS = {
    "left": 3,
    "right": 72,
    "top": 8,
    "bottom": 97,
}

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
_CJK_FONT_PROP: Optional[fm.FontProperties] = None
_FACIAL_LABEL_OFFSETS = {
    "右眼": (8.0, -4.0),
    "左眼": (-8.0, -4.0),
    "鼻子": (0.0, -1.8),
    "右脸颊": (11.0, 1.5),
    "左脸颊": (-11.0, 1.5),
}

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


def _get_cjk_font_prop() -> Optional[fm.FontProperties]:
    global _CJK_FONT_PROP
    if _CJK_FONT_PROP is not None:
        return _CJK_FONT_PROP

    try:
        for entry in fm.fontManager.ttflist:
            if entry.name in _CJK_FONT_CANDIDATES:
                _CJK_FONT_PROP = fm.FontProperties(fname=entry.fname)
                return _CJK_FONT_PROP

        for font_path in fm.findSystemFonts():
            lowered = font_path.lower()
            if (
                "notosanscjk" in lowered
                or "sourcehansans" in lowered
                or "wqy-zenhei" in lowered
                or "wqy-microhei" in lowered
                or "simhei" in lowered
                or "msyh" in lowered
                or "yahei" in lowered
                or "pingfang" in lowered
                or "heiti" in lowered
            ):
                _CJK_FONT_PROP = fm.FontProperties(fname=font_path)
                return _CJK_FONT_PROP
    except Exception:
        return None

    return None


def _roi_label_points_for_docx(report: Dict[str, Any]) -> list[Dict[str, Any]]:
    analysis = report.get("analysis") if isinstance(report, dict) else None
    if not isinstance(analysis, dict):
        return []
    roi_analysis = analysis.get("roi_analysis")
    if not isinstance(roi_analysis, dict):
        return []
    roi_list = roi_analysis.get("roi_list")
    if not isinstance(roi_list, list):
        return []

    points: list[Dict[str, Any]] = []
    for item in roi_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            mean_c = float(item.get("mean_c"))
        except Exception:
            continue

        center_x = item.get("center_x_pct")
        center_y = item.get("center_y_pct")
        if center_x is None or center_y is None:
            continue
        try:
            cx = max(0.0, min(100.0, float(center_x)))
            cy = max(0.0, min(100.0, float(center_y)))
        except Exception:
            continue

        x = THERMAL_PLOT_BOUNDS["left"] + (cx / 100.0) * (
            THERMAL_PLOT_BOUNDS["right"] - THERMAL_PLOT_BOUNDS["left"]
        )
        y = THERMAL_PLOT_BOUNDS["top"] + (cy / 100.0) * (
            THERMAL_PLOT_BOUNDS["bottom"] - THERMAL_PLOT_BOUNDS["top"]
        )
        label_x = x
        label_y = y
        for key, (dx, dy) in _FACIAL_LABEL_OFFSETS.items():
            if key in name:
                label_x = max(2.0, min(98.0, x + dx))
                label_y = max(2.0, min(98.0, y + dy))
                break

        points.append(
            {
                "name": name,
                "mean_c": mean_c,
                "x": x,
                "y": y,
                "label_x": label_x,
                "label_y": label_y,
            }
        )

    points.sort(key=lambda p: p["label_y"])
    min_y_gap = 3.2
    for i in range(1, len(points)):
        prev = points[i - 1]
        cur = points[i]
        if abs(cur["label_x"] - prev["label_x"]) < 8 and (cur["label_y"] - prev["label_y"]) < min_y_gap:
            cur["label_y"] = min(97.0, prev["label_y"] + min_y_gap)
    return points


def _render_labeled_thermal_image_for_docx(base_image: Path, report: Dict[str, Any]) -> Optional[Path]:
    points = _roi_label_points_for_docx(report)
    if not points:
        return base_image

    try:
        cjk_font = _get_cjk_font_prop()
        image = plt.imread(str(base_image))
        fig, ax = plt.subplots(figsize=(6, 4), dpi=180)
        ax.imshow(image)
        ax.axis("off")

        h, w = image.shape[0], image.shape[1]

        for point in points:
            px = (point["x"] / 100.0) * w
            py = (point["y"] / 100.0) * h
            lpx = (point.get("label_x", point["x"]) / 100.0) * w
            lpy = (point.get("label_y", point["y"]) / 100.0) * h
            text = f"{point['name']} {point['mean_c']:.1f}°C"
            ax.annotate(
                text,
                xy=(px, py),
                xytext=(lpx, lpy),
                textcoords="data",
                fontsize=4,
                fontproperties=cjk_font,
                color="white",
                ha="center",
                va="center",
                arrowprops={
                    "arrowstyle": "-",
                    "color": "#0f172a",
                    "lw": 0.5,
                    "alpha": 0.85,
                },
                bbox={
                    "boxstyle": "round,pad=0.18",
                    "facecolor": "#0f172a",
                    "alpha": 0.72,
                    "edgecolor": "#ffffff",
                    "linewidth": 0.4,
                },
            )

        out_path = base_image.with_name(f"{base_image.stem}_docx_labeled{base_image.suffix}")
        fig.savefig(str(out_path), bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        if out_path.exists() and out_path.is_file():
            return out_path
        return base_image
    except Exception as exc:
        logging.debug("render labeled thermal image failed: %s", exc)
        return base_image


def generate_docx_report(report: Dict[str, Any], emr: Dict[str, Any]) -> Path:
    patient = (report.get("patient") or emr.get("patient") or {})
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}

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
    regional = (analysis.get("regional_comparison") or {}) if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else None
    if isinstance(abnormal_regions, list) and abnormal_regions:
        body_part = (report.get("patient") or emr.get("patient") or {}).get("body_part")
        rendered = False
        for item in abnormal_regions:
            region = str(item.get("region", "-") or "-")
            if region in _EXCLUDED_REPORT_REGIONS:
                continue
            region_cn = str(item.get("region_cn") or "").strip() or _region_to_body_part_cn(region, body_part)
            status = str(item.get("status", "-")).upper()
            avg_c = _fmt_temp(item.get("avg_c"))
            delta_c = _fmt_temp(item.get("delta_c"))
            doc.add_paragraph(
                f"{region_cn}（{region}）: 状态 {status}，均温 {avg_c}°C，Δ {delta_c}°C",
                style="List Bullet",
            )
            rendered = True
        if not rendered:
            doc.add_paragraph("未发现明显异常区域")
    else:
        doc.add_paragraph("未发现明显异常区域")

    doc.add_heading("风险等级", level=2)
    doc.add_paragraph(str(analysis.get("risk_level", "-")).upper())

    doc.add_heading("诊断结论", level=2)
    diagnosis_text = report.get("diagnosis") or emr.get("diagnosis") or "-"
    doc.add_paragraph(_strip_think(str(diagnosis_text)))

    doc.add_heading("医生意见", level=2)
    doc.add_paragraph(_strip_think(str(report.get("doctor_opinion") or "-")))

    ai_payload = report.get("ai") or {}
    if not ai_payload and is_llm_enabled():
        try:
            ai_payload = generate_report_ai(report, emr)
            if ai_payload:
                report.setdefault("ai", ai_payload)
        except Exception as exc:
            logging.exception("LLM report generation failed: %s", exc)
    ai_plan_text = ""
    plan = report.get("treatment_plan") or emr.get("treatment_plan") or {}
    if isinstance(plan, dict):
        ai_plan_text = str(plan.get("ai_recommendation") or "").strip()
    if not ai_plan_text:
        ai_plan_text = str(ai_payload.get("treatment_plan_text") or "").strip()
        if ai_plan_text and isinstance(plan, dict):
            plan["ai_recommendation"] = ai_plan_text
    ai_report_note = str(ai_payload.get("report_note") or "").strip()

    if ai_plan_text:
        ai_plan_text = _strip_think(ai_plan_text.replace("AI", "").replace("ＡＩ", "").strip())
    if ai_report_note:
        ai_report_note = _strip_think(ai_report_note.replace("AI", "").replace("ＡＩ", "").strip())

    if ai_plan_text:
        doc.add_heading("治疗方案建议", level=2)
        doc.add_paragraph(ai_plan_text)

    if ai_report_note:
        doc.add_heading("补充说明", level=2)
        doc.add_paragraph(ai_report_note)

    image_path = report.get("thermal_roi_labeled_image") or report.get("thermal_marked_image")
    image_file = _resolve_image_file(str(image_path or "")) if image_path else None
    if image_file is None:
        thermal_images = report.get("thermal_images") if isinstance(report, dict) else None
        if isinstance(thermal_images, list):
            for item in thermal_images:
                image_file = _resolve_image_file(str(item or ""))
                if image_file is not None:
                    break

    doc.add_heading("热成像图", level=2)
    if image_file is not None:
        labeled_image = _render_labeled_thermal_image_for_docx(image_file, report)
        doc.add_picture(str(labeled_image or image_file), width=Inches(5.5))
    else:
        doc.add_paragraph("热成像图文件未找到")

    doc.save(str(output_path))
    print(f"[DOCX] Saved report to: {output_path}")
    return output_path
