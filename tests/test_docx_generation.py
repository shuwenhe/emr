#!/usr/bin/env python3
"""
直接测试DOCX报告生成函数。
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, "/home/shuwen/emr/backend")
sys.path.insert(0, "/home/shuwen/emr/ingestion")

from app.config import DATA_DIR
from reports.python import generate_docx_report

# 使用最近的分析记录
record_id = "de0029fb-a72f-41ff-a8ba-1b38650f63c1"
record_dir = DATA_DIR / record_id

print(f"=== 测试 generate_docx_report ===")
print(f"Record ID: {record_id}")
print()

# 加载报告和EMR
with open(record_dir / "report.json") as f:
    report = json.load(f)

# 构造最小的EMR对象
patient = report.get("patient") or {}
emr = {
    "emr_id": f"EMR-TEST-{record_id}",
    "patient": patient,
    "created_at": report.get("created_at"),
}

print(f"Report has thermal_images: {len(report.get('thermal_images', []))} images")
print(f"Report keys: {list(report.keys())[:8]}")
print()

try:
    print("调用 generate_docx_report()...")
    result = generate_docx_report(report, emr)
    print(f"✓ 成功！返回值类型: {type(result)}")
    print(f"  返回值: {result}")
    if result:
        path = Path(result)
        if path.exists():
            print(f"  ✓ 文件存在，大小: {path.stat().st_size} bytes")
        else:
            print(f"  ✗ 文件不存在: {path}")
except Exception as e:
    print(f"✗ 异常: {e}")
    import traceback
    traceback.print_exc()
