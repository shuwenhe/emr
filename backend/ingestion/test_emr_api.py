#!/usr/bin/env python3
"""
快速测试API是否正确返回EMR数据
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.emr import list_emrs
from app.data_platform import list_emrs as list_db_emrs

def main():
    patient_id = "P6977C107E19C"
    patient_name = "侯宝玉"
    
    print("=" * 70)
    print(f"测试: {patient_name} (ID: {patient_id}) 的EMR数据")
    print("=" * 70)
    
    # 测试文件系统查询
    print(f"\n[文件系统查询]")
    fs_emrs = list_emrs(patient_id=patient_id, include_archived=False)
    print(f"  返回的EMR数: {len(fs_emrs)}")
    if fs_emrs:
        for i, emr in enumerate(fs_emrs, 1):
            print(f"  {i}. EMR-{emr.get('emr_id')} | {emr.get('created_at')} | {emr.get('diagnosis', '待诊断')[:30]}")
    
    # 测试数据库查询
    print(f"\n[数据库查询]")
    try:
        db_emrs = list_db_emrs(patient_id=patient_id, include_archived=False,  limit=100)
        print(f"  返回的EMR数: {len(db_emrs)}")
        if db_emrs:
            for i, emr in enumerate(db_emrs[:10], 1):  # 只显示前10条
                emr_id = emr.get('emr_id') if isinstance(emr, dict) else emr['emr_id']
                print(f"  {i}. {emr_id}")
    except Exception as e:
        print(f"  错误: {e}")
    
    print(f"\n[API测试代码]")
    code_sample = '''
在 FastAPI main.py 中，list_emr_endpoint 应该这样调用:

@app.get("/emr")
def list_emr_endpoint(patient_id: str | None = None, include_archived: bool = False):
    # 使用 emr.py 中的 list_emrs 函数，它从文件系统读取
    emrs = list_emrs(patient_id=patient_id, include_archived=include_archived)
    # 如果从文件系统找不到，尝试从数据库代理查询
    if patient_id and not emrs:
        patient = get_patient(patient_id)
        patient_name = patient.get("name") if patient else None
        if patient_name:
            fallback = list_emrs(patient_id=None, include_archived=include_archived)
            emrs = [
                item
                for item in fallback
                if (item.get("patient") or dict()).get("name") == patient_name
            ]
    return emrs

前端调用: GET /emr?patient_id=P6977C107E19C
期望返回: ''' + str(len(fs_emrs)) + ''' 条 EMR 记录的 JSON 数组
    '''
    print(code_sample)
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
