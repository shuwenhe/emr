#!/usr/bin/env python3
"""
批量为所有EMR记录生成模板报告文件
解决患者侯宝玉只有1个报告的问题
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from app.data_platform import list_emrs as list_db_emrs, get_patient
from app.report_template import generate_template_report

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_reports_for_patient(patient_id: str, patient_name: str):
    """为某个患者的所有EMR生成模板报告"""
    
    print(f"\n{'='*70}")
    print(f"为患者 {patient_name} (ID: {patient_id}) 生成报告")
    print(f"{'='*70}")
    
    # 获取患者的所有EMR
    try:
        emrs = list_db_emrs(patient_id=patient_id, limit=1000, include_archived=False)
        print(f"\n[计数] 找到 {len(emrs)} 条 EMR 记录")
    except Exception as e:
        logger.error(f"获取EMR失败: {e}")
        return
    
    if not emrs:
        print(f"✗ 没有找到任何EMR记录")
        return
    
    success_count = 0
    fail_count = 0
    
    # 为每条EMR生成报告
    for i, emr in enumerate(emrs, 1):
        try:
            emr_id = emr.get("emr_id", f"EMR-{i}")
            created_at = emr.get("created_at", "")
            diagnosis = emr.get("diagnosis", "")[:50]
            
            # 构造report和emr对象（generate_template_report期望的格式）
            report = emr.get("report", {})
            if not report:
                # 如果没有report字段，用EMR数据填充
                report = {
                    "patient": emr.get("patient"),
                    "created_at": emr.get("created_at"),
                    "diagnosis": emr.get("diagnosis"),
                    "doctor_opinion": emr.get("doctor_opinion"),
                    "thermal_marked_image": emr.get("thermal_marked_image"),
                    "report_id": f"RPT-{emr_id}",
                    "analysis": {}
                }
            
            # 生成模板报告文件
                report_path = generate_template_report(report, emr)
            print(f"  {i:2}. ✓ {emr_id:16} | {created_at:19} | {diagnosis:50}")
                print(f"       └─> {report_path.name}")
            success_count += 1
            
        except Exception as e:
            logger.error(f"  {i:2}. ✗ {emr.get('emr_id', 'Unknown')} - 生成失败: {e}")
            fail_count += 1
    
    print(f"\n[结果统计]")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  总计: {len(emrs)}")
    
    return success_count, fail_count

def main():
    """为所有患者生成报告"""
    
    print("=" * 70)
    print("模板报告批量生成工具")
    print("=" * 70)
    
    # 目标患者
    target_patients = {
        "P6977C107E19C": "侯宝玉",
        # 可以添加其他患者
    }
    
    total_success = 0
    total_fail = 0
    
    for patient_id, patient_name in target_patients.items():
        try:
            success, fail = generate_reports_for_patient(patient_id, patient_name) or (0, 0)
            total_success += success
            total_fail += fail
        except Exception as e:
            logger.error(f"处理患者 {patient_name} 时出错: {e}")
    
    print(f"\n{'='*70}")
    print(f"[全局统计]")
    print(f"  成功生成: {total_success}")
    print(f"  失败: {total_fail}")
    print(f"  总计: {total_success + total_fail}")
    print(f"{'='*70}")
    print(f"\n✅ 报告生成完成！")
    print(f"   报告文件位置: /Users/shuwen/hospital-report/reports/")
    print(f"   前端应该能看到所有生成的报告文件")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
