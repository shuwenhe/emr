#!/usr/bin/env python3
"""
同步EMR文件中的患者信息到数据库
解决患者侯宝玉的12条诊断报告无法显示的问题
"""

import sys
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# 使用项目根目录下的EMR数据目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMR_DIR = PROJECT_ROOT / "data" / "emr"
from app.data_platform import upsert_patient, list_emrs as list_db_emrs, get_patient

def main():
    """从EMR JSON文件同步患者信息到数据库"""
    
    print("=" * 60)
    print("EMR患者同步工具")
    print("=" * 60)
    
    # 1. 收集EMR文件中的所有患者
    patients_from_emr = defaultdict(dict)
    
    print(f"\n[1] 扫描EMR文件目录: {EMR_DIR}")
    emr_files = list(EMR_DIR.glob("EMR-*.json"))
    print(f"    找到 {len(emr_files)} 个EMR文件")
    
    for emr_file in sorted(emr_files):
        try:
            with open(emr_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            patient_info = data.get("patient") or {}
            patient_id = patient_info.get("patient_id")
            
            if patient_id:
                # 保留最新的患者信息
                if patient_id not in patients_from_emr or \
                   data.get("created_at", "") > patients_from_emr[patient_id].get("created_at", ""):
                    patients_from_emr[patient_id] = {
                        "patient_id": patient_id,
                        "name": patient_info.get("name"),
                        "gender": patient_info.get("gender"),
                        "age": patient_info.get("age"),
                        "created_at": data.get("created_at"),
                        "emr_count": patients_from_emr[patient_id].get("emr_count", 0) + 1,
                    }
                else:
                    patients_from_emr[patient_id]["emr_count"] += 1
        except Exception as e:
            print(f"    ⚠️  错误: 无法读取 {emr_file.name}: {e}")
    
    print(f"\n[2] 从EMR中提取患者信息:")
    for patient_id, info in sorted(patients_from_emr.items()):
        print(f"    - {info['name']} (ID: {patient_id}, 年龄: {info['age']}, EMR数: {info['emr_count']})")
    
    # 2. 检查数据库中的患者
    print(f"\n[3] 检查数据库患者记录:")
    db_patients = {}
    for patient_id in patients_from_emr.keys():
        patient = get_patient(patient_id)
        if patient:
            db_patients[patient_id] = patient
            print(f"    ✓ {patient_id}: {patient.get('name')} (已在数据库)")
        else:
            print(f"    ✗ {patient_id}: {patients_from_emr[patient_id]['name']} (数据库中缺失)")
    
    # 3. 同步患者信息到数据库
    print(f"\n[4] 同步患者信息到数据库:")
    synced_count = 0
    for patient_id, info in patients_from_emr.items():
        if patient_id not in db_patients:
            try:
                upsert_patient({
                    "patient_id": patient_id,
                    "name": info["name"],
                    "gender": info["gender"],
                    "age": info["age"],
                    "payload_json": json.dumps(info),
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                print(f"    ✓ 已添加: {patient_id} - {info['name']}")
                synced_count += 1
            except Exception as e:
                print(f"    ✗ 失败: {patient_id} - {e}")
    
    # 4. 验证：检查侯宝玉的记录
    print(f"\n[5] 验证特定患者(侯宝玉):")
    target_patient_ids = [pid for pid, info in patients_from_emr.items() if info['name'] == '侯宝玉']
    
    for patient_id in target_patient_ids:
        patient = get_patient(patient_id)
        if patient:
            print(f"    ✓ 患者 {patient['name']} (ID: {patient_id}) 已在数据库")
            # 查询该患者的所有EMR
            db_emrs = list_db_emrs(patient_id=patient_id)
            print(f"      数据库中的EMR记录: {len(db_emrs)} 条")
        else:
            print(f"    ✗ 患者 {patients_from_emr[patient_id]['name']} (ID: {patient_id}) 仍未在数据库")
    
    print(f"\n[6] 统计:")
    print(f"    - EMR中的患者总数: {len(patients_from_emr)}")
    print(f"    - 数据库中已有: {len(db_patients)}")
    print(f"    - 本次同步: {synced_count}")
    print(f"    - 侯宝玉的EMR文件数: {patients_from_emr.get(next((pid for pid, info in patients_from_emr.items() if info['name'] == '侯宝玉'), None), {}).get('emr_count', 0)}")
    
    print("\n" + "=" * 60)
    print("同步完成！请刷新前端患者列表")
    print("=" * 60)

if __name__ == "__main__":
    main()
