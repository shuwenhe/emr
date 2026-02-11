import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATA_DIR
from .data_platform import save_plan, save_report


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


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

    payload_path = _find_payload_file(record_dir)
    image_paths = [str(path) for path in _find_image_files(record_dir)]

    temps: List[float] = []
    if payload_path.suffix.lower() == ".csv":
        temps = _load_csv_temperatures(payload_path)

    metrics = _summarize_temperatures(temps)
    avg_temp = metrics["avg_c"]
    risk_level = _risk_level(avg_temp)

    capture_time = (metadata.get("capture") or {}).get("capture_time") or datetime.now().isoformat()
    device = metadata.get("device") or {}
    patient = metadata.get("patient") or {}
    clinical = metadata.get("clinical") or {}
    body_part = patient.get("body_part") or "unknown"

    summary = "temperature metrics unavailable"
    key_findings = [summary]
    if metrics["count"]:
        summary = f"temperature range {metrics['min_c']}C - {metrics['max_c']}C"
        key_findings = [
            summary,
            f"average temperature {metrics['avg_c']}C",
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
        "diagnosis": diagnosis,
        "doctor_opinion": doctor_opinion,
        "analysis": {
            "overall_score": score,
            "risk_level": risk_level,
            "summary": summary,
            "key_findings": key_findings,
            "temperature_metrics": metrics,
            "qc": {"issues": []},
        },
    }

    intensity = 2
    if risk_level == "high":
        intensity = 1
    elif risk_level == "low":
        intensity = 3

    plan = {
        "plan_id": plan_id,
        "record_id": record_id,
        "created_at": capture_time,
        "therapy_type": "moxibustion",
        "intensity_level": intensity,
        "sessions": 6,
        "frequency": "every_2_days",
        "target_regions": [
            {
                "region": body_part,
                "duration_min": 8 + intensity,
                "target_temp_c": round(42 + intensity, 1),
                "distance_cm": 3.0,
            }
        ],
        "safety_limits": {
            "max_temp_c": 49.0,
            "max_duration_min": 20,
        },
        "notes": "test plan generated by analysis stub",
    }

    report["treatment_plan"] = plan

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
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    save_report(record_id, report)
    save_plan(record_id, plan)

    return {
        "report": report,
        "plan": plan,
        "dispatch": dispatch,
        "payload_path": str(payload_path),
    }
