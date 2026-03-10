#!/usr/bin/env python3
"""
测试 generate_docx_report 和异常处理。
"""
import sys
sys.path.insert(0, "/home/shuwen/emr/backend/ingestion")
sys.path.insert(0, "/home/shuwen/emr/backend")

import logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

from pathlib import Path
from app.config import DATA_DIR
import json

record_id = "de0029fb-a72f-41ff-a8ba-1b38650f63c1"
record_dir = DATA_DIR / record_id

print(f"Record dir: {record_dir}")

try:
    # 简化：不加载完整JSON，只测试函数
    from backend.reports.docx_generator import generate_docx_report
    
    # 构造最小化的测试数据
    report = {
        "report_id": "test-report",
        "patient": {"name": "test-patient"},
        "created_at": "2026-03-10T14:53:00",
        "analysis": {"temperature_metrics": {"min_c": 30, "max_c": 40}},
        "thermal_images": ["de0029fb-a72f-41ff-a8ba-1b38650f63c1/thermal_roi_labeled.png"],
    }
    
    emr = {
        "emr_id": "EMR-test",
        "patient": {"name": "test-patient"},
    }
    
    print("\n生成报告...") 
    result = generate_docx_report(report, emr)
    print(f"返回值: {result}")
    print(f"类型: {type(result)}")
    
    if result and Path(result).exists():
        print(f"✓ 文件存在: {Path(result).stat().st_size} bytes")
    else:
        print(f"✗ 文件不存在或值为空")
        
except Exception as e:
    print(f"异常: {e}")
    import traceback
    traceback.print_exc()
