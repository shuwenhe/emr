import csv
import importlib
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import urllib.error
import urllib.request

import re
import yaml

import matplotlib
import numpy as np
from matplotlib import font_manager as fm

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .config import DATA_DIR
from .data_platform import get_patient_history, save_plan, save_report
from .emr import upsert_emr_from_analysis
from .clickhouse_store import insert_thermal_csv

THERMAL_PLOT_BOUNDS = {
    "left": 3,
    "right": 72,
    "top": 8,
    "bottom": 97,
}

FACIAL_LABEL_OFFSETS = {
    "右眼": (15.0, -10.0),
    "左眼": (-15.0, -10.0),
    "鼻子": (0.0, 8.0),
    "右脸颊": (18.0, 5.0),
    "左脸颊": (-18.0, 5.0),
    "额头": (0.0, -12.0),
    "口部": (0.0, 10.0),
}

_HEAD_LABEL_KEYWORDS = (
    "眼",
    "鼻",
    "额",
    "颞",
    "口",
    "唇",
    "脸",
    "颊",
    "耳",
    "头",
    "下颌",
    "颏",
)

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

# 添加ROI目录用于导入ROI模块（优先新结构 roi/python，兼容旧结构 scripts）
_BASE_DIR = Path(__file__).resolve().parents[3]
_ROI_PY_DIR = _BASE_DIR / "roi" / "python"
_LEGACY_SCRIPTS_DIR = _BASE_DIR / "scripts"
for _import_dir in (_ROI_PY_DIR, _LEGACY_SCRIPTS_DIR):
    if _import_dir.exists() and str(_import_dir) not in sys.path:
        sys.path.insert(0, str(_import_dir))

BASE_DIR = _BASE_DIR
TREATMENT_RULES_PATH = BASE_DIR / "config" / "treatment_rules.yaml"


def _load_treatment_rules() -> dict:
    if not TREATMENT_RULES_PATH.exists():
        raise FileNotFoundError(f"Treatment rules not found: {TREATMENT_RULES_PATH}")
    with TREATMENT_RULES_PATH.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    return payload


_TREATMENT_RULES = _load_treatment_rules()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"
THERMAL_DTYPE = np.float32
THERMAL_RENDER_DPI = int(os.getenv("THERMAL_RENDER_DPI", "100"))
_ROI_MODULE_BINDINGS: Optional[Dict[str, Any]] = None
_ROI_MODULE_IMPORT_ERROR: Optional[str] = None
_ROI_MODULE_LOCK = threading.Lock()


def _get_roi_module_bindings() -> Optional[Dict[str, Any]]:
    global _ROI_MODULE_BINDINGS, _ROI_MODULE_IMPORT_ERROR

    if _ROI_MODULE_BINDINGS is not None:
        return _ROI_MODULE_BINDINGS
    if _ROI_MODULE_IMPORT_ERROR is not None:
        return None

    with _ROI_MODULE_LOCK:
        if _ROI_MODULE_BINDINGS is not None:
            return _ROI_MODULE_BINDINGS
        if _ROI_MODULE_IMPORT_ERROR is not None:
            return None

        try:
            roi_module = importlib.import_module("roi_mediapipe_dynamic")
            _ROI_MODULE_BINDINGS = {
                "detect_landmarks": getattr(roi_module, "detect_landmarks"),
                "build_dynamic_rois": getattr(roi_module, "build_dynamic_rois"),
                "to_rgb": getattr(roi_module, "to_rgb"),
                "calc_stats": getattr(roi_module, "calc_stats"),
            }
            logging.info("ROI modules imported and cached successfully")
            return _ROI_MODULE_BINDINGS
        except (ImportError, AttributeError) as e:
            _ROI_MODULE_IMPORT_ERROR = str(e)
            logging.warning(f"ROI modules not available, skipping ROI analysis: {e}")
            return None


def _extract_json_block(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _ollama_generate(prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
    if not OLLAMA_ENABLED:
        return ""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
        result = json.loads(body)
        return str(result.get("response") or "").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        logging.error(f"Ollama generate error: {type(e).__name__}: {e}")
        logging.error(f"Model: {OLLAMA_MODEL}, URL: {OLLAMA_BASE_URL}")
        return ""


def _build_llm_context(
    patient: Dict[str, Any],
    body_part: str,
    summary: str,
    risk_level: str,
    metrics: Dict[str, Any],
    abnormal_regions: List[Dict[str, Any]],
    roi_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    lines = [
        "你是一名医疗热成像评估助手。请基于以下信息生成简洁、谨慎的中文内容。"
        "输出只需客观结论，避免夸大或绝对化表述。",
        f"患者信息：姓名={patient.get('name','-')} 性别={patient.get('gender','-')} 年龄={patient.get('age','-')} 部位={body_part}",
        f"风险等级：{risk_level}",
        f"温度摘要：{summary}",
        f"温度指标：min={metrics.get('min_c')} max={metrics.get('max_c')} avg={metrics.get('avg_c')}",
    ]
    
    # 添加ROI分析信息（如果可用）
    if roi_analysis and roi_analysis.get("roi_list"):
        lines.append("")
        lines.append("身体部位温度分析（MediaPipe姿态识别）：")
        roi_list = roi_analysis.get("roi_list", [])
        # 取前5个最热的部位
        for roi in roi_list[:5]:
            lines.append(f"  - {roi['name']}: {roi['mean_c']}°C (±{roi['std_c']}, n={roi['count']})")
        
        # 添加对称性信息
        roi_dict = {roi['name']: roi for roi in roi_list}
        symmetry_pairs = [
            ("左眼", "右眼"),
            ("左脸颊", "右脸颊"),
            ("左臂", "右臂"),
            ("左腿", "右腿"),
        ]
        has_asymmetry = False
        for left_name, right_name in symmetry_pairs:
            if left_name in roi_dict and right_name in roi_dict:
                left_temp = roi_dict[left_name].get("mean_c", 0)
                right_temp = roi_dict[right_name].get("mean_c", 0)
                diff = abs(left_temp - right_temp)
                if diff > 0.5:
                    lines.append(f"  左右对比：{left_name}({left_temp}°C) vs {right_name}({right_temp}°C)，温差{diff:.2f}°C")
                    has_asymmetry = True
        
        if not has_asymmetry:
            lines.append("  左右对称性：良好")

    lines.append(f"异常区域：{abnormal_regions}")
    return "\n".join(lines)


def _generate_llm_diagnosis_and_opinion(context: str) -> Dict[str, str]:
    prompt = (
        context
        + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note。"
        "其中 doctor_opinion 和 report_note 需明确‘仅供参考’。"
    )
    text = _ollama_generate(prompt, temperature=0.2, max_tokens=400)
    data = _extract_json_block(text) or {}
    return {
        "diagnosis": str(data.get("diagnosis") or "").strip(),
        "doctor_opinion": str(data.get("doctor_opinion") or "").strip(),
        "report_note": str(data.get("report_note") or "").strip(),
    }


def _generate_llm_plan_text(context: str, plan: Dict[str, Any]) -> str:
    plan_summary = {
        "intensity_level": plan.get("intensity_level"),
        "sessions": plan.get("sessions"),
        "frequency": plan.get("frequency"),
        "target_regions": plan.get("target_regions"),
        "acupoints": plan.get("acupoints"),
    }
    prompt = (
        context
        + "以下为规则引擎生成的治疗方案要点，请生成精简中文说明（3-6句），并标注‘仅供参考’：\n"
        + json.dumps(plan_summary, ensure_ascii=False)
    )
    return _ollama_generate(prompt, temperature=0.3, max_tokens=300)


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def _select_acupoints(
    diagnosis: str,
    body_part: str,
    abnormal_regions: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    text = f"{diagnosis} {body_part}".lower()
    points: List[Dict[str, str]] = []

    def add_point(name: str, reason: str) -> None:
        if any(item["name"] == name for item in points):
            return
        points.append({"name": name, "reason": reason})

    for rule in _TREATMENT_RULES.get("keywords", []):
        keyword = str(rule.get("keyword", "")).lower()
        if keyword and keyword in text:
            for item in rule.get("points", []):
                add_point(str(item.get("name", "")), str(item.get("reason", "")))

    if not points:
        region_rules = _TREATMENT_RULES.get("region_rules", [])
        for region_item in abnormal_regions:
            region = str(region_item.get("region") or "").lower()
            for rule in region_rules:
                matches = [str(item).lower() for item in rule.get("match", [])]
                if any(match and match in region for match in matches):
                    for item in rule.get("points", []):
                        add_point(str(item.get("name", "")), str(item.get("reason", "")))

    if not points:
        for item in _TREATMENT_RULES.get("defaults", []):
            add_point(str(item.get("name", "")), str(item.get("reason", "")))

    return points


def _build_treatment_plan(
    record_id: str,
    plan_id: str,
    capture_time: str,
    diagnosis: str,
    body_part: str,
    risk_level: str,
    abnormal_regions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    params = _TREATMENT_RULES.get("parameters", {})
    risk_params = params.get("risk_levels", {})
    risk_cfg = risk_params.get(risk_level, risk_params.get("unknown", {}))

    intensity = int(risk_cfg.get("intensity_level", 2))
    sessions = int(risk_cfg.get("sessions", 6))
    frequency = str(risk_cfg.get("frequency", "every_2_days"))

    target_cfg = params.get("target_region", {})
    base_duration = int(target_cfg.get("base_duration_min", 8))
    duration_step = int(target_cfg.get("duration_per_intensity", 1))
    base_temp = float(target_cfg.get("base_target_temp_c", 42))
    temp_step = float(target_cfg.get("temp_per_intensity", 1.0))
    distance_cm = float(target_cfg.get("distance_cm", 3.0))

    target_regions: List[Dict[str, Any]] = []
    used_regions: set[str] = set()
    for item in abnormal_regions:
        region = str(item.get("region") or "").strip()
        if not region or region in used_regions:
            continue
        used_regions.add(region)
        target_regions.append(
            {
                "region": region,
                "duration_min": base_duration + intensity * duration_step,
                "target_temp_c": round(base_temp + intensity * temp_step, 1),
                "distance_cm": distance_cm,
            }
        )

    if not target_regions:
        target_regions.append(
            {
                "region": body_part,
                "duration_min": base_duration + intensity * duration_step,
                "target_temp_c": round(base_temp + intensity * temp_step, 1),
                "distance_cm": distance_cm,
            }
        )

    acupoints = _select_acupoints(diagnosis, body_part, abnormal_regions)
    course_template = str(
        params.get(
            "course_template",
            "建议 {sessions} 次为一疗程，频次 {frequency}，根据反应调整强度与时间。",
        )
    )
    course_recommendation = course_template.format(
        sessions=sessions,
        frequency=frequency,
        intensity=intensity,
    )

    safety_cfg = params.get("safety_limits", {})
    max_temp_c = float(safety_cfg.get("max_temp_c", 49.0))
    max_duration_min = int(safety_cfg.get("max_duration_min", 20))

    return {
        "plan_id": plan_id,
        "record_id": record_id,
        "created_at": capture_time,
        "therapy_type": "moxibustion",
        "intensity_level": intensity,
        "sessions": sessions,
        "frequency": frequency,
        "target_regions": target_regions,
        "acupoints": acupoints,
        "course_recommendation": course_recommendation,
        "safety_limits": {
            "max_temp_c": max_temp_c,
            "max_duration_min": max_duration_min,
        },
        "notes": "根据诊断结果自动生成",
    }


def _find_payload_file(record_dir: Path) -> Path:
    image_exts = {".png", ".jpg", ".jpeg"}
    csv_candidates: List[Path] = []
    other_candidates: List[Path] = []
    for item in record_dir.iterdir():
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        if suffix == ".json" or suffix in image_exts:
            continue
        if suffix == ".csv":
            csv_candidates.append(item)
        else:
            other_candidates.append(item)

    if csv_candidates:
        matrix_candidates = [p for p in csv_candidates if p.stem.endswith("_matrix")]
        if matrix_candidates:
            return sorted(matrix_candidates)[0]
        return sorted(csv_candidates)[0]

    if other_candidates:
        return sorted(other_candidates)[0]

    raise FileNotFoundError("payload_file_not_found")


def _find_image_files(record_dir: Path) -> List[Path]:
    image_exts = {".png", ".jpg", ".jpeg"}
    return [
        item
        for item in record_dir.iterdir()
        if item.is_file() and item.suffix.lower() in image_exts
    ]


def _load_csv_temperatures(file_path: Path) -> List[float]:
    temps: List[float] = []
    has_temperature_column = False
    with open(file_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            has_temperature_column = has_temperature_column or ("temperature_c" in row)
            value = row.get("temperature_c")
            if value is None:
                continue
            try:
                temps.append(float(value))
            except ValueError:
                continue
    if temps:
        return temps
    return temps


def _load_csv_grid(file_path: Path) -> Optional[np.ndarray]:
    rows: List[int] = []
    cols: List[int] = []
    temps: List[float] = []
    has_row_col_columns = False
    with open(file_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            has_row_col_columns = has_row_col_columns or ("row" in row and "col" in row and "temperature_c" in row)
            try:
                r = int(row.get("row", ""))
                c = int(row.get("col", ""))
                t = float(row.get("temperature_c", ""))
            except (TypeError, ValueError):
                continue
            rows.append(r)
            cols.append(c)
            temps.append(t)

    if not rows or not cols or not temps:
        if not has_row_col_columns:
            try:
                matrix = np.loadtxt(str(file_path), delimiter=",", dtype=THERMAL_DTYPE)
                if matrix.ndim == 1:
                    matrix = matrix.reshape(1, -1)
                if matrix.ndim == 2:
                    return matrix
            except Exception:
                return None
        return None

    max_r = max(rows)
    max_c = max(cols)
    grid = np.full((max_r + 1, max_c + 1), np.nan, dtype=THERMAL_DTYPE)
    row_idx = np.asarray(rows, dtype=np.int32)
    col_idx = np.asarray(cols, dtype=np.int32)
    temp_values = np.asarray(temps, dtype=THERMAL_DTYPE)
    grid[row_idx, col_idx] = temp_values
    return grid


def _summarize_grid_temperatures(grid: np.ndarray) -> Dict[str, Optional[float]]:
    if grid.size == 0:
        return {
            "min_c": None,
            "max_c": None,
            "avg_c": None,
            "count": 0,
        }

    valid_mask = ~np.isnan(grid)
    count = int(np.count_nonzero(valid_mask))
    if count == 0:
        return {
            "min_c": None,
            "max_c": None,
            "avg_c": None,
            "count": 0,
        }

    return {
        "min_c": round(float(np.nanmin(grid)), 2),
        "max_c": round(float(np.nanmax(grid)), 2),
        "avg_c": round(float(np.nanmean(grid)), 2),
        "count": count,
    }


def _generate_marked_image(
    grid: np.ndarray,
    output_path: Path,
    roi_analysis: Optional[Dict[str, Any]] = None,
    draw_roi_labels: bool = False,
) -> Optional[str]:
    """生成标注热图
    
    Args:
        grid: 温度矩阵
        output_path: 输出路径
        roi_analysis: ROI分析结果（仅在draw_roi_labels=True时使用）
        draw_roi_labels: 是否绘制ROI标签（默认False，避免重复叠加）
    """
    if grid.size == 0 or np.all(np.isnan(grid)):
        return None

    masked = np.ma.masked_invalid(grid)
    min_val = float(np.nanmin(grid))
    max_val = float(np.nanmax(grid))

    fig, ax = plt.subplots(figsize=(6, 4), dpi=THERMAL_RENDER_DPI)
    im = ax.imshow(masked, cmap="inferno")
    ax.set_title("Infrared Thermal Map")
    ax.axis("off")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Temperature (°C)")

    ax.text(
        0.02,
        0.98,
        f"Max: {max_val:.2f}°C",
        transform=ax.transAxes,
        va="top",
        ha="left",
        color="white",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.5),
    )
    ax.text(
        0.02,
        0.90,
        f"Min: {min_val:.2f}°C",
        transform=ax.transAxes,
        va="top",
        ha="left",
        color="white",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.5),
    )

    # 仅在明确要求时才绘制ROI标签，以避免重复叠加
    if draw_roi_labels:
        points = _roi_label_points(roi_analysis)
        if points:
            cjk_font = _get_cjk_font_prop()
            rows, cols = grid.shape
            for point in points:
                px = (point["x"] / 100.0) * max(cols - 1, 1)
                py = (point["y"] / 100.0) * max(rows - 1, 1)
                lpx = (point.get("label_x", point["x"]) / 100.0) * max(cols - 1, 1)
                lpy = (point.get("label_y", point["y"]) / 100.0) * max(rows - 1, 1)
                text = f"{point['name']} {point['mean_c']:.1f}°C"
                ax.annotate(
                    text,
                    xy=(px, py),
                    xytext=(lpx, lpy),
                    textcoords="data",
                    fontsize=7.5,  # 保持小字号便于阅读
                    fontproperties=cjk_font,
                    color="white",
                    ha="center",
                    va="center",
                    arrowprops={
                        "arrowstyle": "->",
                        "color": "#ffffff",
                        "lw": 1.0,
                        "alpha": 0.7,
                    },
                    bbox={
                        "boxstyle": "round,pad=0.35",
                        "facecolor": "#1e293b",
                        "alpha": 0.85,
                        "edgecolor": "#ffffff",
                        "linewidth": 0.8,
                    },
                )

    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def _extract_temperature_labels(image_path: Optional[str]) -> Dict[str, Any]:
    if not image_path:
        return {"text": None, "values": []}
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return {"text": None, "values": []}

    try:
        text = pytesseract.image_to_string(Image.open(image_path))
    except Exception:
        return {"text": None, "values": []}

    values = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text or "")]
    return {"text": text, "values": values}


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


def _roi_label_points(roi_analysis: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(roi_analysis, dict):
        return []
    roi_list = roi_analysis.get("roi_list")
    if not isinstance(roi_list, list):
        return []

    points: List[Dict[str, Any]] = []
    for item in roi_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            mean_c = float(item.get("mean_c"))
            cx = max(0.0, min(100.0, float(item.get("center_x_pct"))))
            cy = max(0.0, min(100.0, float(item.get("center_y_pct"))))
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
        for key, (dx, dy) in FACIAL_LABEL_OFFSETS.items():
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

    # 改进的标签位置调整算法，避免重叠
    points.sort(key=lambda p: p["label_y"])
    min_y_gap = 6.5  # 增加垂直间距
    min_x_threshold = 18.0  # 增加水平检测范围
    
    for i in range(1, len(points)):
        cur = points[i]
        max_prev_y = -1.0
        
        for j in range(i):
            prev = points[j]
            x_dist = abs(cur["label_x"] - prev["label_x"])
            y_dist = cur["label_y"] - prev["label_y"]
            
            # 如果水平位置接近且垂直间距不足，需要调整
            if x_dist < min_x_threshold and y_dist < min_y_gap:
                max_prev_y = max(max_prev_y, prev["label_y"])
        
        if max_prev_y >= 0:
            cur["label_y"] = min(95.0, max_prev_y + min_y_gap)

    # 特别处理头部区域的标签，使其更整齐
    head_points: List[Dict[str, Any]] = []
    for point in points:
        name = str(point.get("name") or "")
        is_head = point["y"] <= 40.0 or any(key in name for key in _HEAD_LABEL_KEYWORDS)
        if is_head:
            head_points.append(point)

    if head_points:
        head_points.sort(key=lambda p: p["label_x"])
        min_head_x_gap = 12.0  # 增加水平间距
        for idx in range(1, len(head_points)):
            prev = head_points[idx - 1]
            cur = head_points[idx]
            if (cur["label_x"] - prev["label_x"]) < min_head_x_gap:
                cur["label_x"] = min(96.0, prev["label_x"] + min_head_x_gap)

        # 根据位置分两行显示头部标签，避免拥挤
        base_y = 8.0
        for idx, point in enumerate(head_points):
            # 交替分两行，左边的标签在上，右边的在下，形成错落布局
            row_offset = 0 if idx % 2 == 0 else 7.0
            point["label_y"] = max(2.0, min(22.0, base_y + row_offset))
    
    return points


def _generate_roi_labeled_image(
    base_image_path: Optional[str],
    roi_analysis: Optional[Dict[str, Any]],
    output_path: Path,
) -> Optional[str]:
    if not base_image_path:
        logging.info("ROI labeled image: no base_image_path provided")
        return None
    points = _roi_label_points(roi_analysis)
    if not points:
        logging.info("ROI labeled image: no label points extracted from roi_analysis")
        return None

    try:
        logging.info(f"Generating ROI labeled image with {len(points)} points to {output_path}")
        cjk_font = _get_cjk_font_prop()
        image = plt.imread(str(base_image_path))
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
                fontsize=7.5,  # 增大字号便于阅读
                fontproperties=cjk_font,
                color="white",
                ha="center",
                va="center",
                arrowprops={
                    "arrowstyle": "->",  # 使用箭头样式更明确
                    "color": "#ffffff",
                    "lw": 1.0,  # 增加线条粗细
                    "alpha": 0.7,
                },
                bbox={
                    "boxstyle": "round,pad=0.35",  # 增加内边距
                    "facecolor": "#1e293b",  # 深色背景
                    "alpha": 0.85,  # 提高不透明度
                    "edgecolor": "#ffffff",
                    "linewidth": 0.8,
                },
            )

        fig.savefig(str(output_path), bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        if output_path.exists() and output_path.is_file():
            logging.info(f"ROI labeled image generated successfully: {output_path}")
            return str(output_path)
        logging.warning(f"ROI labeled image file not found after saving: {output_path}")
        return None
    except Exception as exc:
        logging.error(f"generate ROI labeled image failed: {exc}", exc_info=True)
        return None


def _compare_temp(value: Optional[float], baseline: Optional[float], delta: float = 0.3) -> str:
    if value is None or baseline is None:
        return "unknown"
    if value > baseline + delta:
        return "high"
    if value < baseline - delta:
        return "low"
    return "normal"


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


def _region_analysis(grid: np.ndarray, baseline: Optional[float]) -> List[Dict[str, Any]]:
    if grid.size == 0 or np.all(np.isnan(grid)):
        return []

    rows, cols = grid.shape
    row_step = max(rows // 3, 1)
    col_step = max(cols // 3, 1)
    regions: List[Dict[str, Any]] = []

    for r_idx in range(3):
        r_start = r_idx * row_step
        r_end = rows if r_idx == 2 else min((r_idx + 1) * row_step, rows)
        for c_idx in range(3):
            c_start = c_idx * col_step
            c_end = cols if c_idx == 2 else min((c_idx + 1) * col_step, cols)
            region_code = f"r{r_idx + 1}_c{c_idx + 1}"
            if region_code in _EXCLUDED_REPORT_REGIONS:
                continue
            block = grid[r_start:r_end, c_start:c_end]
            avg = float(np.nanmean(block)) if not np.all(np.isnan(block)) else None
            regions.append(
                {
                    "region": region_code,
                    "avg_c": round(avg, 2) if avg is not None else None,
                    "status": _compare_temp(avg, baseline),
                }
            )

    return regions


def _summarize_temperatures(temps: List[float]) -> Dict[str, Optional[float]]:
    if not temps:
        return {
            "min_c": None,
            "max_c": None,
            "avg_c": None,
            "count": 0,
        }
    return {
        "min_c": round(min(temps), 2),
        "max_c": round(max(temps), 2),
        "avg_c": round(sum(temps) / len(temps), 2),
        "count": len(temps),
    }


def _risk_level(avg_temp: Optional[float]) -> str:
    if avg_temp is None:
        return "unknown"
    if avg_temp >= 38.0:
        return "high"
    if avg_temp >= 36.5:
        return "medium"
    return "low"


def _fallback_roi_analysis(matrix: np.ndarray) -> Dict[str, Any]:
    """
    当 MediaPipe 不可用时，使用固定区域进行基础温度分析
    返回预定义区域的温度统计
    """
    h, w = matrix.shape
    roi_list = []
    
    # 定义固定区域（百分比坐标），调整为更精确的面部区域
    fixed_regions = [
        {"name": "额头", "x_pct": (35, 65), "y_pct": (8, 18)},
        {"name": "右眼", "x_pct": (32, 45), "y_pct": (20, 32)},
        {"name": "左眼", "x_pct": (55, 68), "y_pct": (20, 32)},
        {"name": "鼻子", "x_pct": (44, 56), "y_pct": (32, 48)},
        {"name": "右脸颊", "x_pct": (22, 42), "y_pct": (38, 58)},
        {"name": "左脸颊", "x_pct": (58, 78), "y_pct": (38, 58)},
        {"name": "口部", "x_pct": (42, 58), "y_pct": (52, 65)},
    ]
    
    for region in fixed_regions:
        try:
            x_start = int(w * region["x_pct"][0] / 100)
            x_end = int(w * region["x_pct"][1] / 100)
            y_start = int(h * region["y_pct"][0] / 100)
            y_end = int(h * region["y_pct"][1] / 100)
            
            roi_data = matrix[y_start:y_end, x_start:x_end]
            valid_data = roi_data[~np.isnan(roi_data)]
            
            if len(valid_data) > 0:
                center_x_pct = (region["x_pct"][0] + region["x_pct"][1]) / 2
                center_y_pct = (region["y_pct"][0] + region["y_pct"][1]) / 2
                
                roi_list.append({
                    "name": region["name"],
                    "count": len(valid_data),
                    "mean_c": round(float(np.mean(valid_data)), 2),
                    "min_c": round(float(np.min(valid_data)), 2),
                    "max_c": round(float(np.max(valid_data)), 2),
                    "std_c": round(float(np.std(valid_data)), 2),
                    "center_x_pct": center_x_pct,
                    "center_y_pct": center_y_pct,
                })
        except Exception as e:
            logging.debug(f"Failed to analyze region {region['name']}: {e}")
            continue
    
    if not roi_list:
        return None
    
    # 按平均温度排序
    roi_list.sort(key=lambda x: x["mean_c"], reverse=True)
    
    return {
        "roi_list": roi_list,
        "hottest_temp": roi_list[0]["mean_c"] if roi_list else None,
        "coolest_temp": roi_list[-1]["mean_c"] if roi_list else None,
    }


def _analyze_roi_regions(
    payload_path: Path,
    csv_is_matrix: bool = True,
    matrix: Optional[np.ndarray] = None,
) -> Optional[Dict[str, Any]]:
    """
    使用MediaPipe + ROI系统分析热成像数据
    返回14个身体部位的温度统计，如果失败返回None
    """
    roi_bindings = _get_roi_module_bindings()
    if not roi_bindings:
        return None
    detect_landmarks = roi_bindings["detect_landmarks"]
    build_dynamic_rois = roi_bindings["build_dynamic_rois"]
    to_rgb = roi_bindings["to_rgb"]
    calc_stats = roi_bindings["calc_stats"]
    
    try:
        # 优先复用调用方已加载的矩阵，避免重复IO与内存分配
        if matrix is None:
            if csv_is_matrix:
                matrix = np.loadtxt(str(payload_path), delimiter=",", dtype=THERMAL_DTYPE)
                if matrix.ndim != 2:
                    return None
            else:
                # 如果是标准CSV表格，转换为矩阵
                grid = _load_csv_grid(payload_path)
                if grid is None:
                    return None
                matrix = grid

        if matrix.dtype != THERMAL_DTYPE:
            matrix = matrix.astype(THERMAL_DTYPE, copy=False)
        
        h, w = matrix.shape
        
        # 关键点检测
        rgb = to_rgb(matrix, vmin=28, vmax=40, cmap_name="inferno")
        landmarks = detect_landmarks(rgb)
        
        if not landmarks:
            logging.debug("No landmarks detected in ROI analysis")
            return None
        
        # 构建ROI
        rois = build_dynamic_rois(h, w, landmarks)
        
        # 计算统计
        roi_stats = {}
        roi_list = []
        
        for roi_name, mask in rois.items():
            ys, xs = np.where(mask)
            if xs.size == 0 or ys.size == 0:
                continue

            values = matrix[ys, xs]
            center_x_pct = None
            center_y_pct = None
            center_x_pct = round(float(xs.mean()) / max(w - 1, 1) * 100.0, 2)
            center_y_pct = round(float(ys.mean()) / max(h - 1, 1) * 100.0, 2)
            
            stats = calc_stats(values)
            roi_stats[roi_name] = stats
            roi_list.append({
                "name": roi_name,
                "count": stats.get("count", 0),
                "mean_c": round(stats.get("mean", 0), 2),
                "min_c": round(stats.get("min", 0), 2),
                "max_c": round(stats.get("max", 0), 2),
                "std_c": round(stats.get("std", 0), 2),
                "center_x_pct": center_x_pct,
                "center_y_pct": center_y_pct,
            })
            del values

        del rois
        
        if not roi_list:
            return None
        
        # 按平均温度排序
        roi_list.sort(key=lambda x: x["mean_c"], reverse=True)
        
        return {
            "roi_stats": roi_stats,
            "roi_list": roi_list,
            "total_rois": len(roi_list),
            "hottest_region": roi_list[0]["name"] if roi_list else None,
            "hottest_temp": roi_list[0]["mean_c"] if roi_list else None,
            "coolest_region": roi_list[-1]["name"] if roi_list else None,
            "coolest_temp": roi_list[-1]["mean_c"] if roi_list else None,
        }
    except Exception as exc:
        message = str(exc)
        if "mediapipe" in message.lower() and (
            "solutions" in message.lower() or "legacy" in message.lower()
        ):
            logging.warning(f"ROI analysis skipped due to MediaPipe compatibility: {exc}")
        else:
            logging.error(f"ROI analysis failed: {exc}")
        # 使用 fallback 方法进行基础区域分析
        try:
            if matrix is not None and matrix.ndim == 2:
                logging.info("Using fallback ROI analysis with fixed regions")
                return _fallback_roi_analysis(matrix)
            if csv_is_matrix:
                fallback_matrix = np.loadtxt(str(payload_path), delimiter=",", dtype=THERMAL_DTYPE)
                if fallback_matrix.ndim == 2:
                    logging.info("Using fallback ROI analysis with fixed regions")
                    return _fallback_roi_analysis(fallback_matrix)
        except Exception as fallback_exc:
            logging.error(f"Fallback ROI analysis also failed: {fallback_exc}")
        return None


def analyze_record(record_id: str) -> Dict[str, Any]:
    record_dir = DATA_DIR / record_id
    if not record_dir.exists():
        raise FileNotFoundError("record_not_found")

    metadata_path = record_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError("metadata_not_found")

    with open(metadata_path, "r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    payload_path = None
    try:
        payload_path = _find_payload_file(record_dir)
    except FileNotFoundError:
        payload_path = None
    image_paths = [str(path) for path in _find_image_files(record_dir)]

    grid: Optional[np.ndarray] = None
    temps: List[float] = []
    if payload_path and payload_path.suffix.lower() == ".csv":
        grid = _load_csv_grid(payload_path)
        if grid is not None:
            metrics = _summarize_grid_temperatures(grid)
        else:
            temps = _load_csv_temperatures(payload_path)
            metrics = _summarize_temperatures(temps)
    else:
        metrics = _summarize_temperatures(temps)
    avg_temp = metrics["avg_c"]
    risk_level = _risk_level(avg_temp)
    body_avg_temp_c = avg_temp
    patient = metadata.get("patient") or {}
    body_part = patient.get("body_part") or "unknown"

    marked_image_path = None
    base_marked_image_path = None
    roi_labeled_image_path = None
    temperature_labels = {"text": None, "values": []}
    region_comparison: List[Dict[str, Any]] = []
    abnormal_regions: List[Dict[str, Any]] = []
    roi_analysis: Optional[Dict[str, Any]] = None
    if payload_path and payload_path.suffix.lower() == ".csv":
        if grid is not None:
            region_comparison = _region_analysis(grid, body_avg_temp_c)
            abnormal_regions = [
                {
                    "region": item["region"],
                    "region_cn": _region_to_body_part_cn(item["region"], body_part),
                    "status": item["status"],
                    "avg_c": item["avg_c"],
                    "delta_c": round(item["avg_c"] - body_avg_temp_c, 2)
                    if item.get("avg_c") is not None and body_avg_temp_c is not None
                    else None,
                }
                for item in region_comparison
                if item.get("status") in {"high", "low"}
            ]
        # 尝试进行ROI分析
        roi_analysis = _analyze_roi_regions(payload_path, csv_is_matrix=True, matrix=grid)
        logging.info(f"ROI analysis result: {'success' if roi_analysis else 'failed or None'}, has {len(roi_analysis.get('roi_list', [])) if roi_analysis else 0} ROIs")
        
        if grid is not None:
            # 生成基础热图（不绘制ROI标签，避免后续重复叠加）
            marked_image_path = _generate_marked_image(
                grid,
                record_dir / "thermal_marked.png",
                roi_analysis=None,  # 不在这里绘制ROI标签
            )
            if marked_image_path:
                base_marked_image_path = marked_image_path
                relative_path = Path(marked_image_path).relative_to(DATA_DIR)
                image_paths.append(str(relative_path))
                temperature_labels = _extract_temperature_labels(marked_image_path)

        # 如果有ROI分析结果，生成带ROI标签的图像（小字体、清晰标注，只有这一层）
        if marked_image_path and roi_analysis:
            logging.info(f"Generating small-font ROI labeled image with base: {marked_image_path}")
            roi_labeled_image_path = _generate_roi_labeled_image(
                marked_image_path,
                roi_analysis,
                record_dir / "thermal_roi_labeled.png",
            )
            if roi_labeled_image_path:
                relative_roi_path = Path(roi_labeled_image_path).relative_to(DATA_DIR)
                image_paths.append(str(relative_roi_path))
        else:
            logging.info(f"Skipping ROI labeled image (only basic thermal): marked_image_path={bool(marked_image_path)}, roi_analysis={bool(roi_analysis)}")

    capture_time = (metadata.get("capture") or {}).get("capture_time") or datetime.now().isoformat()
    device = metadata.get("device") or {}
    clinical = metadata.get("clinical") or {}
    patient_id = patient.get("patient_id")

    summary = "温度指标不可用"
    key_findings = [summary]
    if metrics["count"]:
        summary = f"温度范围 {metrics['min_c']}C - {metrics['max_c']}C"
        key_findings = [
            summary,
            f"平均温度 {metrics['avg_c']}C",
        ]

    score = None
    if metrics["min_c"] is not None and metrics["max_c"] is not None:
        score = round((metrics["max_c"] - metrics["min_c"]) * 10, 1)

    report_id = f"RPT-{record_id}"
    plan_id = f"PLAN-{record_id}"

    doctor_opinion = clinical.get("doctor_opinion")
    diagnosis = clinical.get("diagnosis")

    llm_context = _build_llm_context(
        patient=patient,
        body_part=body_part,
        summary=summary,
        risk_level=risk_level,
        metrics=metrics,
        abnormal_regions=abnormal_regions,
        roi_analysis=roi_analysis,
    )
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context) if OLLAMA_ENABLED else {}
    ai_diagnosis = str(llm_result.get("diagnosis") or "").strip()
    ai_doctor_opinion = str(llm_result.get("doctor_opinion") or "").strip()
    ai_report_note = str(llm_result.get("report_note") or "").strip()

    if not diagnosis and ai_diagnosis:
        diagnosis = ai_diagnosis
    if not doctor_opinion and ai_doctor_opinion:
        doctor_opinion = ai_doctor_opinion

    if not doctor_opinion:
        doctor_opinion = f"基于热成像温度分布评估，风险等级为 {risk_level}，建议结合临床进一步判断。"

    if not diagnosis:
        diagnosis = summary if summary else "影像学提示无明显异常"

    history_records = []
    if patient_id:
        history_records = get_patient_history(
            patient_id=patient_id,
            exclude_record_id=record_id,
            limit=5,
        )

    report = {
        "report_id": report_id,
        "record_id": record_id,
        "created_at": capture_time,
        "patient": {
            "patient_id": patient.get("patient_id"),
            "name": patient.get("name"),
            "gender": patient.get("gender"),
            "age": patient.get("age"),
            "body_part": body_part,
            "posture": patient.get("posture"),
        },
        "clinical": {
            "chief_complaint": clinical.get("chief_complaint"),
            "past_history": clinical.get("past_history") or [],
            "family_history": clinical.get("family_history") or [],
            "allergies": clinical.get("allergies") or [],
            "medications": clinical.get("medications") or [],
        },
        "device": device,
        "capture": metadata.get("capture"),
        "environment": metadata.get("environment"),
        "thermal_images": image_paths,
        "thermal_marked_image": str(Path(base_marked_image_path).relative_to(DATA_DIR)) if base_marked_image_path else (str(Path(marked_image_path).relative_to(DATA_DIR)) if marked_image_path else None),
        "thermal_roi_labeled_image": str(Path(roi_labeled_image_path).relative_to(DATA_DIR)) if roi_labeled_image_path else None,
        "thermal_marked_labels": temperature_labels,
        "diagnosis": diagnosis,
        "doctor_opinion": doctor_opinion,
        "history": {
            "patient_id": patient_id,
            "records": history_records,
        },
        "analysis": {
            "overall_score": score,
            "risk_level": risk_level,
            "summary": summary,
            "key_findings": key_findings,
            "temperature_metrics": metrics,
            "body_avg_temp_c": body_avg_temp_c,
            "regional_comparison": {
                "baseline_avg_c": body_avg_temp_c,
                "regions": region_comparison,
                "abnormal_regions": abnormal_regions,
            },
            "roi_analysis": roi_analysis,
            "qc": {"issues": []},
        },
    }

    plan = _build_treatment_plan(
        record_id,
        plan_id,
        capture_time,
        diagnosis,
        body_part,
        risk_level,
        abnormal_regions,
    )

    ai_plan_text = ""
    if OLLAMA_ENABLED:
        ai_plan_text = _generate_llm_plan_text(llm_context, plan).strip()
        if ai_plan_text:
            plan["ai_recommendation"] = ai_plan_text

    report["treatment_plan"] = plan

    if OLLAMA_ENABLED and (ai_diagnosis or ai_doctor_opinion or ai_plan_text or ai_report_note):
        report["ai"] = {
            "model": OLLAMA_MODEL,
            "diagnosis": ai_diagnosis,
            "doctor_opinion": ai_doctor_opinion,
            "treatment_plan_text": ai_plan_text,
            "report_note": ai_report_note,
        }

    intensity = plan["intensity_level"]
    dispatch = {
        "dispatch_id": f"DISPATCH-{record_id}",
        "plan_id": plan_id,
        "device_id": device.get("device_id"),
        "sent_at": (_parse_iso_datetime(capture_time) + timedelta(minutes=5)).isoformat(timespec="seconds"),
        "payload": {
            "mode": "moxibustion",
            "intensity_level": intensity,
            "steps": [
                {
                    "step": 1,
                    "region": body_part,
                    "duration_min": plan["target_regions"][0]["duration_min"],
                    "target_temp_c": plan["target_regions"][0]["target_temp_c"],
                    "distance_cm": plan["target_regions"][0]["distance_cm"],
                }
            ],
        },
    }

    for name, payload in (
        ("report.json", report),
        ("plan.json", plan),
        ("dispatch.json", dispatch),
    ):
        with open(record_dir / name, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)

    save_report(record_id, report)
    save_plan(record_id, plan)
    
    # Write CSV data to ClickHouse if exists
    csv_files = list(record_dir.glob("*.csv"))
    for csv_file in csv_files:
        try:
            insert_thermal_csv(
                record_id=record_id,
                metadata=metadata,
                data_path=str(csv_file),
                frame_id=csv_file.stem
            )
        except Exception as exc:
            logging.warning("ClickHouse ingest failed for %s: %s", csv_file.name, exc)
    
    try:
        upsert_emr_from_analysis(record_id, report, plan, metadata)
    except Exception as exc:
        logging.exception("EMR upsert and report generation failed for record %s: %s", record_id, exc)

    return {
        "report": report,
        "plan": plan,
        "dispatch": dispatch,
        "payload_path": str(payload_path) if payload_path else None,
    }
