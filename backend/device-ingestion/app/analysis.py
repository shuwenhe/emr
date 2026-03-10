import csv
import json
import logging
import os
import sys
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
    "右眼": (8.0, -4.0),
    "左眼": (-8.0, -4.0),
    "鼻子": (0.0, -1.8),
    "右脸颊": (11.0, 1.5),
    "左脸颊": (-11.0, 1.5),
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

# 添加scripts目录用于导入ROI模块
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

BASE_DIR = Path(__file__).resolve().parents[3]
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
    context = (
        "你是一名医疗热成像评估助手。请基于以下信息生成简洁、谨慎的中文内容。"
        "输出只需客观结论，避免夸大或绝对化表述。\n"
        f"患者信息：姓名={patient.get('name','-')} 性别={patient.get('gender','-')} 年龄={patient.get('age','-')} 部位={body_part}\n"
        f"风险等级：{risk_level}\n"
        f"温度摘要：{summary}\n"
        f"温度指标：min={metrics.get('min_c')} max={metrics.get('max_c')} avg={metrics.get('avg_c')}\n"
    )
    
    # 添加ROI分析信息（如果可用）
    if roi_analysis and roi_analysis.get("roi_list"):
        context += "\n身体部位温度分析（MediaPipe姿态识别）：\n"
        roi_list = roi_analysis.get("roi_list", [])
        # 取前5个最热的部位
        for roi in roi_list[:5]:
            context += f"  - {roi['name']}: {roi['mean_c']}°C (±{roi['std_c']}, n={roi['count']})\n"
        
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
                    context += f"  左右对比：{left_name}({left_temp}°C) vs {right_name}({right_temp}°C)，温差{diff:.2f}°C\n"
                    has_asymmetry = True
        
        if not has_asymmetry:
            context += "  左右对称性：良好\n"
    
    context += f"异常区域：{abnormal_regions}\n"
    return context


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

    if not has_temperature_column:
        try:
            matrix = np.loadtxt(str(file_path), delimiter=",")
            if matrix.ndim == 1:
                matrix = matrix.reshape(1, -1)
            if matrix.ndim == 2:
                return matrix.flatten().tolist()
        except Exception:
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
                matrix = np.loadtxt(str(file_path), delimiter=",")
                if matrix.ndim == 1:
                    matrix = matrix.reshape(1, -1)
                if matrix.ndim == 2:
                    return matrix
            except Exception:
                return None
        return None

    max_r = max(rows)
    max_c = max(cols)
    grid = np.full((max_r + 1, max_c + 1), np.nan, dtype=float)
    for r, c, t in zip(rows, cols, temps):
        grid[r, c] = t
    return grid


def _generate_marked_image(grid: np.ndarray, output_path: Path) -> Optional[str]:
    if grid.size == 0 or np.all(np.isnan(grid)):
        return None

    masked = np.ma.masked_invalid(grid)
    min_val = float(np.nanmin(grid))
    max_val = float(np.nanmax(grid))

    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
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

    points.sort(key=lambda p: p["label_y"])
    min_y_gap = 3.2
    for i in range(1, len(points)):
        prev = points[i - 1]
        cur = points[i]
        if abs(cur["label_x"] - prev["label_x"]) < 8 and (cur["label_y"] - prev["label_y"]) < min_y_gap:
            cur["label_y"] = min(97.0, prev["label_y"] + min_y_gap)
    return points


def _generate_roi_labeled_image(
    base_image_path: Optional[str],
    roi_analysis: Optional[Dict[str, Any]],
    output_path: Path,
) -> Optional[str]:
    if not base_image_path:
        return None
    points = _roi_label_points(roi_analysis)
    if not points:
        return None

    try:
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
                fontsize=5,
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

        fig.savefig(str(output_path), bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        if output_path.exists() and output_path.is_file():
            return str(output_path)
        return None
    except Exception as exc:
        logging.debug("generate ROI labeled image failed: %s", exc)
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
    row_splits = np.array_split(np.arange(rows), 3)
    col_splits = np.array_split(np.arange(cols), 3)
    regions: List[Dict[str, Any]] = []

    for r_idx, r_group in enumerate(row_splits, start=1):
        for c_idx, c_group in enumerate(col_splits, start=1):
            region_code = f"r{r_idx}_c{c_idx}"
            if region_code in _EXCLUDED_REPORT_REGIONS:
                continue
            block = grid[np.ix_(r_group, c_group)]
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


def _analyze_roi_regions(payload_path: Path, csv_is_matrix: bool = True) -> Optional[Dict[str, Any]]:
    """
    使用MediaPipe + ROI系统分析热成像数据
    返回14个身体部位的温度统计，如果失败返回None
    """
    try:
        from roi_mediapipe_dynamic import (
            detect_landmarks, build_dynamic_rois, to_rgb, calc_stats
        )
    except ImportError:
        logging.debug("ROI modules not available, skipping ROI analysis")
        return None
    
    try:
        # 尝试加载以二维矩阵形式存储的CSV（非标准表格格式）
        if csv_is_matrix:
            matrix = np.loadtxt(str(payload_path), delimiter=",")
            if matrix.ndim != 2:
                return None
        else:
            # 如果是标准CSV表格，转换为矩阵
            grid = _load_csv_grid(payload_path)
            if grid is None:
                return None
            matrix = grid
        
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
            values = matrix[mask]
            if len(values) == 0:
                continue

            ys, xs = np.where(mask)
            center_x_pct = None
            center_y_pct = None
            if xs.size > 0 and ys.size > 0:
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
        logging.debug(f"ROI analysis failed: {exc}")
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

    temps: List[float] = []
    if payload_path and payload_path.suffix.lower() == ".csv":
        temps = _load_csv_temperatures(payload_path)

    metrics = _summarize_temperatures(temps)
    avg_temp = metrics["avg_c"]
    risk_level = _risk_level(avg_temp)
    body_avg_temp_c = avg_temp
    patient = metadata.get("patient") or {}
    body_part = patient.get("body_part") or "unknown"

    marked_image_path = None
    roi_labeled_image_path = None
    temperature_labels = {"text": None, "values": []}
    region_comparison: List[Dict[str, Any]] = []
    abnormal_regions: List[Dict[str, Any]] = []
    roi_analysis: Optional[Dict[str, Any]] = None
    if payload_path and payload_path.suffix.lower() == ".csv":
        grid = _load_csv_grid(payload_path)
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
            marked_image_path = _generate_marked_image(
                grid, record_dir / "thermal_marked.png"
            )
            if marked_image_path:
                # 转换为相对于DATA_DIR的路径用于API访问
                relative_path = Path(marked_image_path).relative_to(DATA_DIR)
                image_paths.append(str(relative_path))
                temperature_labels = _extract_temperature_labels(marked_image_path)
        
        # 尝试进行ROI分析
        roi_analysis = _analyze_roi_regions(payload_path, csv_is_matrix=True)
        if marked_image_path and roi_analysis:
            roi_labeled_image_path = _generate_roi_labeled_image(
                marked_image_path,
                roi_analysis,
                record_dir / "thermal_roi_labeled.png",
            )
            if roi_labeled_image_path:
                relative_roi_path = Path(roi_labeled_image_path).relative_to(DATA_DIR)
                image_paths.append(str(relative_roi_path))

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
        "thermal_marked_image": str(Path(marked_image_path).relative_to(DATA_DIR)) if marked_image_path else None,
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
    except Exception:
        pass

    return {
        "report": report,
        "plan": plan,
        "dispatch": dispatch,
        "payload_path": str(payload_path) if payload_path else None,
    }
