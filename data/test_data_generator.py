#!/usr/bin/env python3
"""生成测试用的设备原始数据与报告/方案"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

def generate_test_datasets():
    """生成多组测试数据"""
    
    base_path = Path(__file__).parent
    random.seed(42)
    
    # 测试场景配置
    scenarios = [
        {
            "id": "normal_face",
            "device_id": "IR-DEV-0001",
            "device_model": "IR-Thermal-320",
            "device_firmware": "1.2.3",
            "resolution": [320, 240],
            "frame_rate_hz": 9,
            "emissivity": 0.98,
            "ambient_temperature_c": 25.0,
            "humidity_percent": 45.0,
            "airflow": "low",
            "distance_m": 1.2,
            "capture_time": "2026-01-05T13:33:45",
            "subject": {
                "patient_id": "P-0001",
                "gender": "male",
                "age": 47,
                "body_part": "face",
                "posture": "sitting"
            },
            "temp_range": (34.5, 37.5),  # 正常体温范围
            "description": "正常体温的面部采集",
            "symptoms": ["轻微肩颈酸胀"],
            "risk_level": "low",
            "plan_intensity": 2
        },
        {
            "id": "fever_face",
            "device_id": "IR-DEV-0002",
            "device_model": "IR-Thermal-320",
            "device_firmware": "1.2.3",
            "resolution": [320, 240],
            "frame_rate_hz": 9,
            "emissivity": 0.98,
            "ambient_temperature_c": 24.5,
            "humidity_percent": 50.0,
            "airflow": "medium",
            "distance_m": 1.2,
            "capture_time": "2026-01-06T14:22:30",
            "subject": {
                "patient_id": "P-0002",
                "gender": "female",
                "age": 28,
                "body_part": "face",
                "posture": "sitting"
            },
            "temp_range": (38.2, 39.8),  # 发烧体温范围
            "description": "发烧患者的面部采集",
            "symptoms": ["额部灼热感", "轻度头痛"],
            "risk_level": "high",
            "plan_intensity": 1
        },
        {
            "id": "hand_normal",
            "device_id": "IR-DEV-0003",
            "device_model": "IR-Thermal-320",
            "device_firmware": "1.2.3",
            "resolution": [320, 240],
            "frame_rate_hz": 9,
            "emissivity": 0.98,
            "ambient_temperature_c": 23.0,
            "humidity_percent": 40.0,
            "airflow": "low",
            "distance_m": 0.8,
            "capture_time": "2026-01-07T10:15:20",
            "subject": {
                "patient_id": "P-0003",
                "gender": "male",
                "age": 35,
                "body_part": "hand",
                "posture": "sitting"
            },
            "temp_range": (32.0, 34.0),  # 手部体温范围
            "description": "正常手部采集",
            "symptoms": ["手部冰凉"],
            "risk_level": "medium",
            "plan_intensity": 3
        },
        {
            "id": "low_temp",
            "device_id": "IR-DEV-0004",
            "device_model": "IR-Thermal-320",
            "device_firmware": "1.2.3",
            "resolution": [320, 240],
            "frame_rate_hz": 9,
            "emissivity": 0.98,
            "ambient_temperature_c": 22.0,
            "humidity_percent": 55.0,
            "airflow": "low",
            "distance_m": 1.2,
            "capture_time": "2026-01-08T08:45:10",
            "subject": {
                "patient_id": "P-0004",
                "gender": "female",
                "age": 52,
                "body_part": "face",
                "posture": "sitting"
            },
            "temp_range": (33.5, 35.5),  # 体温偏低
            "description": "体温偏低的患者采集",
            "symptoms": ["怕冷", "四肢乏力"],
            "risk_level": "medium",
            "plan_intensity": 3
        }
    ]
    
    for scenario in scenarios:
        # 生成 metadata（与接入服务模型对齐）
        metadata = {
            "device": {
                "device_id": scenario["device_id"],
                "model": scenario["device_model"],
                "firmware": scenario["device_firmware"]
            },
            "capture": {
                "capture_time": scenario["capture_time"],
                "frame_rate_hz": scenario["frame_rate_hz"],
                "resolution": f"{scenario['resolution'][0]}x{scenario['resolution'][1]}",
                "spectral_range": "8-14um",
                "distance_m": scenario["distance_m"],
                "emissivity": scenario["emissivity"]
            },
            "environment": {
                "ambient_temp_c": scenario["ambient_temperature_c"],
                "humidity_percent": scenario["humidity_percent"],
                "airflow": scenario["airflow"]
            },
            "patient": {
                "patient_id": scenario["subject"]["patient_id"],
                "body_part": scenario["subject"]["body_part"],
                "posture": scenario["subject"]["posture"]
            },
            "tags": ["test", scenario["id"]]
        }
        
        # 生成热成像数据
        rows, cols = scenario["resolution"][1], scenario["resolution"][0]
        temp_min, temp_max = scenario["temp_range"]
        
        thermal_data = []
        temp_values = []
        for row in range(rows):
            for col in range(cols):
                # 模拟热成像数据，中心偏热（模拟面部中心温度较高）
                dist_from_center = ((row - rows/2)**2 + (col - cols/2)**2) ** 0.5
                dist_factor = 1 - min(dist_from_center / (rows/2), 1) * 0.5
                
                temp = temp_min + (temp_max - temp_min) * dist_factor
                temp += random.gauss(0, 0.3)  # 添加噪声
                temp_values.append(temp)
                
                thermal_data.append({
                    "row": row,
                    "col": col,
                    "temperature_c": round(temp, 2)
                })

        temp_avg = sum(temp_values) / len(temp_values)
        temp_min_val = min(temp_values)
        temp_max_val = max(temp_values)

        # 生成评估报告
        report_id = f"RPT-{scenario['capture_time'].replace(':', '').replace('-', '').replace('T', '-')}-{scenario['id']}"
        report = {
            "report_id": report_id,
            "case_id": scenario["id"],
            "created_at": scenario["capture_time"],
            "patient": {
                "patient_id": scenario["subject"]["patient_id"],
                "gender": scenario["subject"]["gender"],
                "age": scenario["subject"]["age"],
                "body_part": scenario["subject"]["body_part"],
                "symptoms": scenario["symptoms"]
            },
            "device": metadata["device"],
            "capture": metadata["capture"],
            "environment": metadata["environment"],
            "analysis": {
                "overall_score": round((temp_max_val - temp_min_val) * 10, 1),
                "risk_level": scenario["risk_level"],
                "summary": scenario["description"],
                "key_findings": [
                    f"温度范围 {temp_min_val:.2f}°C - {temp_max_val:.2f}°C",
                    f"平均温度 {temp_avg:.2f}°C"
                ],
                "temperature_metrics": {
                    "min_c": round(temp_min_val, 2),
                    "max_c": round(temp_max_val, 2),
                    "avg_c": round(temp_avg, 2)
                },
                "asymmetry_index": round(random.uniform(0.01, 0.15), 3),
                "qc": {
                    "issues": []
                }
            }
        }

        # 生成灸疗方案
        plan_id = f"PLAN-{scenario['id']}-{scenario['subject']['patient_id']}"
        plan = {
            "plan_id": plan_id,
            "case_id": scenario["id"],
            "created_at": scenario["capture_time"],
            "therapy_type": "moxibustion",
            "intensity_level": scenario["plan_intensity"],
            "sessions": 6,
            "frequency": "every_2_days",
            "target_regions": [
                {
                    "region": scenario["subject"]["body_part"],
                    "duration_min": 8 + scenario["plan_intensity"],
                    "target_temp_c": round(42 + scenario["plan_intensity"], 1),
                    "distance_cm": 3.0
                }
            ],
            "safety_limits": {
                "max_temp_c": 49.0,
                "max_duration_min": 20
            },
            "notes": "测试用方案，请根据实际临床要求调整"
        }

        # 生成下发payload
        dispatch = {
            "dispatch_id": f"DISPATCH-{scenario['id']}-{scenario['subject']['patient_id']}",
            "plan_id": plan_id,
            "device_id": scenario["device_id"],
            "sent_at": (datetime.fromisoformat(scenario["capture_time"]) + timedelta(minutes=5)).isoformat(timespec="seconds"),
            "payload": {
                "mode": "moxibustion",
                "intensity_level": scenario["plan_intensity"],
                "steps": [
                    {
                        "step": 1,
                        "region": scenario["subject"]["body_part"],
                        "duration_min": plan["target_regions"][0]["duration_min"],
                        "target_temp_c": plan["target_regions"][0]["target_temp_c"],
                        "distance_cm": plan["target_regions"][0]["distance_cm"]
                    }
                ]
            }
        }
        
        # 保存文件
        dataset_dir = base_path / scenario["id"]
        dataset_dir.mkdir(exist_ok=True)
        
        # 保存 metadata.json
        metadata_file = dataset_dir / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # 保存热成像数据
        thermal_file = dataset_dir / "frame_0001.csv"
        with open(thermal_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["row", "col", "temperature_c"])
            writer.writeheader()
            writer.writerows(thermal_data)

        # 保存评估报告
        report_file = dataset_dir / "report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 保存灸疗方案
        plan_file = dataset_dir / "plan.json"
        with open(plan_file, 'w', encoding='utf-8') as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

        # 保存下发payload
        dispatch_file = dataset_dir / "dispatch.json"
        with open(dispatch_file, 'w', encoding='utf-8') as f:
            json.dump(dispatch, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 生成测试数据集: {scenario['id']}")
        print(f"  描述: {scenario['description']}")
        print(f"  位置: {dataset_dir}")
        print(f"  数据点: {len(thermal_data)}")
        print()

if __name__ == "__main__":
    print("生成测试数据集...\n")
    generate_test_datasets()
    print("✓ 所有测试数据集生成完成！")
