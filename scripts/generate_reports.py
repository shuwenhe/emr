#!/usr/bin/env python3
"""Generate DOCX reports from test datasets."""

import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from docx import Document


def _load_metadata(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_resolution(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 2:
        return f"{value[0]}x{value[1]}"
    return None


def _normalize_metadata(metadata: Dict) -> Dict[str, Optional[str]]:
    if "device" in metadata:
        device = metadata.get("device") or {}
        capture = metadata.get("capture") or {}
        env = metadata.get("environment") or {}
        patient = metadata.get("patient") or {}
        return {
            "device_id": device.get("device_id"),
            "device_model": device.get("model"),
            "device_firmware": device.get("firmware"),
            "capture_time": capture.get("capture_time"),
            "frame_rate_hz": capture.get("frame_rate_hz"),
            "resolution": capture.get("resolution"),
            "spectral_range": capture.get("spectral_range"),
            "distance_m": capture.get("distance_m"),
            "emissivity": capture.get("emissivity"),
            "ambient_temp_c": env.get("ambient_temp_c"),
            "humidity_percent": env.get("humidity_percent"),
            "airflow": env.get("airflow"),
            "patient_id": patient.get("patient_id"),
            "body_part": patient.get("body_part"),
            "posture": patient.get("posture"),
            "gender": None,
            "age": None,
        }

    subject = metadata.get("subject") or {}
    return {
        "device_id": None,
        "device_model": metadata.get("device_model"),
        "device_firmware": None,
        "capture_time": metadata.get("capture_time"),
        "frame_rate_hz": metadata.get("frame_rate_hz"),
        "resolution": _parse_resolution(metadata.get("resolution")),
        "spectral_range": metadata.get("spectral_range"),
        "distance_m": metadata.get("distance_m"),
        "emissivity": metadata.get("emissivity"),
        "ambient_temp_c": metadata.get("ambient_temperature_c"),
        "humidity_percent": metadata.get("humidity_percent"),
        "airflow": metadata.get("airflow"),
        "patient_id": None,
        "body_part": subject.get("body_part"),
        "posture": subject.get("posture"),
        "gender": subject.get("gender"),
        "age": subject.get("age"),
    }


def _load_temperatures(path: Path) -> List[float]:
    temps: List[float] = []
    with open(path, "r", encoding="utf-8") as handle:
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


def _summarize_temps(temps: List[float]) -> Dict[str, Optional[float]]:
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


def _risk_score(metrics: Dict[str, Optional[float]]) -> int:
    if metrics["avg_c"] is None or metrics["min_c"] is None or metrics["max_c"] is None:
        return 0
    spread = metrics["max_c"] - metrics["min_c"]
    base = max(metrics["avg_c"] - 34.0, 0)
    score = int(base * 4 + spread * 3)
    return max(0, min(score, 30))


def _risk_label(score: int) -> str:
    if score >= 24:
        return "中风险"
    if score >= 12:
        return "低风险"
    return "低风险"


def _build_findings(body_part: Optional[str], score: int) -> List[str]:
    if body_part == "face":
        return [
            f"鼻部充血性改变，鼻部炎性反应（轻度，面积 {score * 5 + 80}）",
            f"口腔周围充血性改变，口腔炎、牙周炎性反应（轻度，面积 {score * 3 + 60}）",
            f"视疲劳、用眼过度、视力下降、眼部炎性反应（中度，不对称性 {score * 2 + 40}）",
        ]
    if body_part == "hand":
        return [
            f"末端循环偏弱，手部寒凉倾向（轻度，面积 {score * 6 + 90}）",
        ]
    if body_part == "shoulder":
        return [
            f"颈部异常热源，考虑颈肌疲劳或肌筋膜炎性反应（轻度，面积 {score * 10 + 300}）",
        ]
    return ["未发现明显风险"]


def _build_detail(body_part: Optional[str]) -> List[str]:
    if body_part == "face":
        return [
            "双眼内眦生理热区扩大 → 视疲劳、用眼过度",
            "鼻部异常高温区 → 鼻部炎性反应",
            "口腔牙区异常热区 → 口腔及牙周炎性反应",
        ]
    if body_part == "hand":
        return [
            "手部末端热区偏低 → 循环偏弱",
            "局部温度不对称 → 使用劳损可能",
        ]
    if body_part == "shoulder":
        return [
            "颈肩部高热态分布或不对称 → 颈肌疲劳或肌筋膜炎性反应",
        ]
    return ["未发现显著异常热区"]


def _build_advice(body_part: Optional[str]) -> Dict[str, List[str]]:
    if body_part == "face":
        return {
            "鼻部": [
                "保持空气流通，避免烟雾、粉尘",
                "适当锻炼，避免冷空气刺激",
                "热蒸汽吸入、加湿、补充水分",
            ],
            "口腔": [
                "注意口腔卫生，规范刷牙",
                "合理饮食，减少甜食",
                "戒烟酒，避免刺激性食物",
                "定期口腔检查",
            ],
            "眼部": [
                "合理用眼，避免长时间近距离用眼",
                "劳逸结合，多做眼保健操",
                "定期视力检查",
            ],
            "颈肩与背部": [
                "保持正确姿势，避免久坐",
                "加强颈肩功能锻炼",
                "必要时至专科进一步检查",
            ],
        }
    return {
        "保健建议": [
            "保持规律作息，适度运动",
            "注意保暖，避免局部受凉",
            "如有不适及时就医",
        ]
    }


def _objective_table(temps: Dict[str, Optional[float]]) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    avg = temps["avg_c"] or 0.0
    front = [
        ("右正面", avg - 2.8),
        ("右头额", avg - 2.6),
        ("右眼睛", avg - 2.7),
        ("鼻", avg - 4.0),
        ("右胸肺", avg + 1.2),
        ("左上腹部", avg + 0.9),
        ("左腹部", avg + 0.2),
    ]
    back = [
        ("右后颈部", avg + 1.6),
        ("右后肩", avg + 0.8),
        ("脊柱", avg + 1.4),
        ("右肾", avg + 1.1),
        ("左肾", avg - 1.8),
    ]
    return front, back


def _build_report(
    dataset_id: str,
    patient_name: str,
    metadata: Dict[str, Optional[str]],
    metrics: Dict[str, Optional[float]],
) -> Document:
    doc = Document()

    score = _risk_score(metrics)
    risk_label = _risk_label(score)
    body_part = metadata.get("body_part")

    doc.add_heading("红外热成像评估报告", level=0)

    doc.add_heading("一、基本信息", level=1)
    doc.add_paragraph(f"姓名：{patient_name}")
    if metadata.get("gender"):
        doc.add_paragraph(f"性别：{metadata['gender']}")
    if metadata.get("age"):
        doc.add_paragraph(f"年龄：{metadata['age']}")
    doc.add_paragraph(f"评估日期：{datetime.now().strftime('%Y-%m-%d')}")
    doc.add_paragraph("报告名称：红外热成像评估报告")
    doc.add_paragraph("英文名称：INFRARED THERMAL IMAGEING HEALTH REPORT")
    doc.add_paragraph("机构：亘颐（上海）科技有限公司")
    doc.add_paragraph("系统：红外影像云平台-红外影像热层析系统")

    doc.add_heading("二、机体功能状态实时热像", level=1)
    if metrics["count"]:
        doc.add_paragraph(f"最大温度：{metrics['max_c']} ℃")
        doc.add_paragraph(f"最小温度：{metrics['min_c']} ℃")
        doc.add_paragraph(f"平均温度：{metrics['avg_c']} ℃")
    else:
        doc.add_paragraph("最大温度：N/A")
        doc.add_paragraph("最小温度：N/A")
        doc.add_paragraph("平均温度：N/A")

    doc.add_paragraph("提示说明：")
    doc.add_paragraph("红外热成像技术是一种功能影像学技术，被动接收人体红外热信号，对人体无任何辐射和伤害。")
    doc.add_paragraph("本报告用于辅助了解健康及亚健康状态，不能替代临床诊断。")
    doc.add_paragraph("若存在脏器切除史，报告中风险提示表示周围组织异常。")

    doc.add_heading("三、风险评估结果", level=1)
    doc.add_heading("1. 头面部", level=2)
    doc.add_paragraph(f"风险等级：{score}（{risk_label}）")
    for item in _build_findings(body_part if body_part == "face" else None, score):
        doc.add_paragraph(f"- {item}")

    doc.add_heading("2. 颈肩部", level=2)
    doc.add_paragraph(f"风险等级：{max(score - 7, 0)}（{risk_label}）")
    for item in _build_findings("shoulder" if body_part == "shoulder" else "shoulder", score // 2):
        doc.add_paragraph(f"- {item}")

    doc.add_heading("3. 胸部", level=2)
    doc.add_paragraph("风险等级：0（低风险）")
    doc.add_paragraph("- 未发现明显风险")

    doc.add_heading("4. 脊柱背部", level=2)
    doc.add_paragraph(f"风险等级：{max(score - 7, 0)}（{risk_label}）")
    doc.add_paragraph(f"- 肩背部明显异常高温，肌筋膜炎性反应（轻度，面积 {score * 10 + 700}）")

    doc.add_heading("四、代谢异常部位热图", level=1)
    doc.add_paragraph("高温区：")
    doc.add_paragraph(f"- 右上腹部（{score * 20 + 500}）")
    doc.add_paragraph(f"- 右腹部（{score * 4 + 90}）")
    doc.add_paragraph(f"- 右后颈部（{score * 5 + 160}）")
    doc.add_paragraph(f"- 右后肩（{score * 15 + 700}）")
    doc.add_paragraph("说明：[xxx] 表示异常区域面积")

    doc.add_heading("五、客观热源数据表（节选）", level=1)
    front, back = _objective_table(metrics)
    doc.add_paragraph("正面（部分）：")
    for label, value in front:
        doc.add_paragraph(f"- {label}：{value:.2f} ℃")
    doc.add_paragraph("背面（部分）：")
    for label, value in back:
        doc.add_paragraph(f"- {label}：{value:.2f} ℃")

    doc.add_heading("六、分部评估详情", level=1)
    doc.add_heading("头面部", level=2)
    for item in _build_detail("face" if body_part == "face" else "face"):
        doc.add_paragraph(f"- {item}")
    doc.add_heading("颈肩部", level=2)
    for item in _build_detail("shoulder"):
        doc.add_paragraph(f"- {item}")
    doc.add_heading("脊柱背部", level=2)
    doc.add_paragraph("- 肩背部片状热区扩大 → 肌筋膜炎性反应")

    doc.add_heading("七、保健建议", level=1)
    for section, items in _build_advice(body_part).items():
        doc.add_heading(section, level=2)
        for idx, item in enumerate(items, start=1):
            doc.add_paragraph(f"{idx}. {item}")

    doc.add_paragraph("")
    doc.add_paragraph(f"评估日期：{datetime.now().strftime('%Y-%m-%d')}")
    doc.add_paragraph("声明：以上为热图所提示可能性，请结合临床进一步诊查。")

    return doc


def generate_reports(
    output_root: Path,
    datasets: List[str],
    patient_name: str,
    data_root: Path,
) -> List[Path]:
    date_folder = datetime.now().strftime("%Y%m%d")
    output_dir = output_root / date_folder
    output_dir.mkdir(parents=True, exist_ok=True)

    created_files: List[Path] = []
    base_time = datetime.now()

    for index, dataset_id in enumerate(datasets):
        dataset_dir = data_root / dataset_id
        metadata_path = dataset_dir / "metadata.json"
        payload_path = dataset_dir / "frame_0001.csv"
        if not metadata_path.exists() or not payload_path.exists():
            continue

        metadata = _normalize_metadata(_load_metadata(metadata_path))
        temps = _load_temperatures(payload_path)
        metrics = _summarize_temps(temps)

        doc = _build_report(dataset_id, patient_name, metadata, metrics)

        timestamp = (base_time + timedelta(seconds=index)).strftime("%Y%m%d_%H%M%S")
        file_name = f"{patient_name}_{timestamp}.docx"
        output_path = output_dir / file_name
        doc.save(output_path)
        created_files.append(output_path)

    return created_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DOCX reports.")
    parser.add_argument("--name", required=True, help="Patient name for file name")
    parser.add_argument(
        "--datasets",
        nargs="+",
        required=True,
        help="Dataset IDs under data/",
    )
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parents[1] / "reports"),
        help="Reports root folder",
    )
    parser.add_argument(
        "--data-root",
        default=str(Path(__file__).resolve().parents[1] / "data"),
        help="Root folder containing test datasets",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root)
    data_root = Path(args.data_root)

    created_files = generate_reports(
        output_root=output_root,
        datasets=args.datasets,
        patient_name=args.name,
        data_root=data_root,
    )

    if not created_files:
        print("No reports generated. Check dataset paths.")
        return

    print("Generated reports:")
    for path in created_files:
        print(path)


if __name__ == "__main__":
    main()
