#!/usr/bin/env python3
"""
完整跟踪EMR和报告生成流程。
"""
import sys
import json
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, "/home/shuwen/emr/backend")
sys.path.insert(0, "/home/shuwen/emr/ingestion")

from app.config import DATA_DIR
from app.emr import upsert_emr_from_analysis

# 使用最近的分析记录
record_id = "de0029fb-a72f-41ff-a8ba-1b38650f63c1"
record_dir = DATA_DIR / record_id

print(f"=== 完整测试 upsert_emr_from_analysis ===")
print(f"Record ID: {record_id}")
print(f"Record dir: {record_dir}")
print(f"Dir exists: {record_dir.exists()}")
print()

try:
    with open(record_dir / "report.json") as f:
        report = json.load(f)
    with open(record_dir / "plan.json") as f:
        plan = json.load(f)
    with open(record_dir / "metadata.json") as f:
        metadata = json.load(f)
    
    print(f"✓ 加载所有必需文件")
    print(f"  - report.json: {len(report)} keys")
    print(f"  - plan.json: {len(plan)} keys")
    print(f"  - metadata.json: {len(metadata)} keys")
    print()
    
    print("调用 upsert_emr_from_analysis()...")
    emr = upsert_emr_from_analysis(record_id, report, plan, metadata)
    
    print(f"✓ 返回成功")
    print(f"  - emr_id: {emr.get('emr_id')}")
    print(f"  - docx_report_path: {emr.get('docx_report_path')}")
    print(f"  - EMR keys: {list(emr.keys())}")
    
    if emr.get('docx_report_path'):
        docx_path = Path(emr.get('docx_report_path'))
        if docx_path.exists():
            print(f"  ✓ DOCX文件存在: {docx_path.stat().st_size} bytes")
        else:
            print(f"  ✗ DOCX路径不存在：{docx_path}")
    else:
        print(f"  ✗ docx_report_path 为 None！")
        
except Exception as e:
    print(f"✗ 异常: {e}")
    import traceback
    traceback.print_exc()
