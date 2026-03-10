#!/usr/bin/env python3
"""
Test EMR generation with detailed logging.
"""
import sys
import json
import logging

# Setup logging to see all messages
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, "/home/shuwen/emr/backend/ingestion")
sys.path.insert(0, "/home/shuwen/emr/backend")

from pathlib import Path
from app.config import DATA_DIR
from app.emr import upsert_emr_from_analysis

record_id = "de0029fb-a72f-41ff-a8ba-1b38650f63c1"
record_dir = DATA_DIR / record_id

print(f"Testing EMR generation for: {record_id}\n")

# Load data
with open(record_dir / "report.json") as f:
    print("Loading report.json...")
    report = json.load(f)

with open(record_dir / "plan.json") as f:
    print("Loading plan.json...")
    plan = json.load(f)

with open(record_dir / "metadata.json") as f:
    print("Loading metadata.json...")
    metadata = json.load(f)

print(f"Loaded: report ({len(report)} keys), plan ({len(plan)} keys), metadata ({len(metadata)} keys)\n")

# Call function with logging
print("=" * 70)
print("Calling upsert_emr_from_analysis()...")
print("=" * 70)
try:
    emr = upsert_emr_from_analysis(record_id, report, plan, metadata)
    print("\n" + "=" * 70)
    print("Result:")
    print(f"  emr_id: {emr.get('emr_id')}")
    print(f"  docx_report_path: {emr.get('docx_report_path')}")
    print("=" * 70)
except Exception as e:
    print(f"\nException: {e}")
    import traceback
    traceback.print_exc()
