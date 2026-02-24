import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import re
import yaml

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .config import DATA_DIR
from .data_platform import get_patient_history, save_plan, save_report
from .emr import upsert_emr_from_analysis

BASE_DIR = Path(__file__).resolve().parents[3]
TREATMENT_RULES_PATH = BASE_DIR / "config" / "treatment_rules.yaml"


def _load_treatment_rules() -> dict:
    if not TREATMENT_RULES_PATH.exists():
        raise FileNotFoundError(f"Treatment rules not found: {TREATMENT_RULES_PATH}")
    with TREATMENT_RULES_PATH.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    return payload


_TREATMENT_RULES = _load_treatment_rules()


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
    for item in record_dir.iterdir():
        if (
            item.is_file()
            and item.suffix.lower() != ".json"
            and item.suffix.lower() not in image_exts
        ):
            return item
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
    with open(file_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            value = row.get("temperature_c")
            if value is None:
                continue
            try:
                temps.append(float(value))
            except ValueError:
                continue
    return temps


def _load_csv_grid(file_path: Path) -> Optional[np.ndarray]:
    rows: List[int] = []
    cols: List[int] = []
    temps: List[float] = []
    with open(file_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
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


def _compare_temp(value: Optional[float], baseline: Optional[float], delta: float = 0.3) -> str:
    if value is None or baseline is None:
        return "unknown"
    if value > baseline + delta:
        return "high"
    if value < baseline - delta:
        return "low"
    return "normal"


def _region_analysis(grid: np.ndarray, baseline: Optional[float]) -> List[Dict[str, Any]]:
    if grid.size == 0 or np.all(np.isnan(grid)):
        return []

    rows, cols = grid.shape
    row_splits = np.array_split(np.arange(rows), 3)
    col_splits = np.array_split(np.arange(cols), 3)
    regions: List[Dict[str, Any]] = []

    for r_idx, r_group in enumerate(row_splits, start=1):
        for c_idx, c_group in enumerate(col_splits, start=1):
            block = grid[np.ix_(r_group, c_group)]
            avg = float(np.nanmean(block)) if not np.all(np.isnan(block)) else None
            regions.append(
                {
                    "region": f"r{r_idx}_c{c_idx}",
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

    marked_image_path = None
    temperature_labels = {"text": None, "values": []}
    region_comparison: List[Dict[str, Any]] = []
    abnormal_regions: List[Dict[str, Any]] = []
    if payload_path and payload_path.suffix.lower() == ".csv":
        grid = _load_csv_grid(payload_path)
        if grid is not None:
            region_comparison = _region_analysis(grid, body_avg_temp_c)
            abnormal_regions = [
                {
                    "region": item["region"],
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

    capture_time = (metadata.get("capture") or {}).get("capture_time") or datetime.now().isoformat()
    device = metadata.get("device") or {}
    patient = metadata.get("patient") or {}
    clinical = metadata.get("clinical") or {}
    body_part = patient.get("body_part") or "unknown"
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
    if not doctor_opinion:
        doctor_opinion = f"基于热成像温度分布评估，风险等级为 {risk_level}，建议结合临床进一步判断。"

    diagnosis = clinical.get("diagnosis")
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

    report["treatment_plan"] = plan

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
