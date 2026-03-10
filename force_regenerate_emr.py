#!/usr/bin/env python3
"""
Force regenerate EMR and DOCX report for a record.
"""
import sys
sys.path.insert(0, "/home/shuwen/emr/backend/ingestion")
sys.path.insert(0, "/home/shuwen/emr/backend")

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

from app.config import DATA_DIR
from app.emr import generate_emr
from app.data_platform import get_emr_by_record_id

record_id = "de0029fb-a72f-41ff-a8ba-1b38650f63c1"

print(f"=" * 70)
print(f"Forcing EMR and DOCX regeneration for: {record_id}")
print(f"=" * 70)

# Check current state
print("\n1. Current EMR state:")
existing = get_emr_by_record_id(record_id)
if existing:
    print(f"   EMR exists:")
    print(f"   - emr_id: {existing.get('emr_id')}")
    print(f"   - docx_report_path: {existing.get('docx_report_path')}")
else:
    print("   No existing EMR")

# Regenerate with force flag
print("\n2. Regenerating EMR with force=True...")
try:
    emr = generate_emr(record_id, force=True)
    print(f"   ✓ EMR generated:")
    print(f"   - emr_id: {emr.get('emr_id')}")
    print(f"   - docx_report_path: {emr.get('docx_report_path')}")
    
    if emr.get('docx_report_path'):
        docx_path = Path(emr.get('docx_report_path'))
        if docx_path.exists():
            print(f"   ✓ DOCX file exists: {docx_path.stat().st_size} bytes")
        else:
            print(f"   ✗ DOCX file not found: {docx_path}")
    else:
        print(f"   ✗ docx_report_path is None")
        
except Exception as e:
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()

print(f"\n" + "=" * 70)
