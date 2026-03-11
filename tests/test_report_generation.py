#!/usr/bin/env python3
"""
测试报告生成流程。
"""
import sys
import json
from pathlib import Path

# 添加路径
sys.path.insert(0, "/home/shuwen/emr/backend")
sys.path.insert(0, "/home/shuwen/emr/ingestion")

from app.config import DATA_DIR
from app.emr import upsert_emr_from_analysis

# 使用最近的分析记录
record_id = "de0029fb-a72f-41ff-a8ba-1b38650f63c1"
record_dir = DATA_DIR / record_id

# 加载报告、计划和元数据
with open(record_dir / "report.json") as f:
    report = json.load(f)

with open(record_dir / "plan.json") as f:
    plan = json.load(f)

with open(record_dir / "metadata.json") as f:
    metadata = json.load(f)

print(f"测试报告生成 - record_id: {record_id}")
print(f"Report keys: {len(report)} (抽样: {list(report.keys())[:5]})")
print(f"Thermal images in report: {report.get('thermal_images', [])[:2]}")
print()

try:
    emr = upsert_emr_from_analysis(record_id, report, plan, metadata)
    print("✓ upsert_emr_from_analysis 成功完成")
    print(f"  - EMR ID: {emr.get('emr_id')}")
    print(f"  - DOCX report path: {emr.get('docx_report_path')}")
    if emr.get('docx_report_path'):
        docx_file = Path(emr.get('docx_report_path'))
        if docx_file.exists():
            print(f"  - DOCX file exists: {docx_file.stat().st_size} bytes")
        else:
            print(f"  ✗ DOCX file does not exist: {docx_file}")
except Exception as e:
    print(f"✗ Error during upsert_emr_from_analysis:")
    import traceback
    traceback.print_exc()
