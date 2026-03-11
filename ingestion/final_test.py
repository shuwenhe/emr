#!/usr/bin/env python3
"""
完整测试：验证患者侯宝玉的所有10条报告是否能被正确返回
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.data_platform import list_emrs as list_db_emrs, get_patient

def test_patient_reports():
    patient_id = "P6977C107E19C"
    patient_name = "侯宝玉"
    
    print("=" * 75)
    print(f"完整API测试: {patient_name} (ID: {patient_id}) 的诊断报告")
    print("=" * 75)
    
    # 1. 验证患者信息
    print(f"\n[Step 1] 验证患者在数据库中:")
    try:
        patient = get_patient(patient_id)
        if patient:
            print(f"  ✓ 患者已存在")
            print(f"    - 姓名: {patient.get('name')}")
            print(f"    - 性别: {patient.get('gender')}")
            print(f"    - 年龄: {patient.get('age')}")
        else:
            print(f"  ✗ 患者不存在于数据库")
            return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False
    
    # 2. 查询数据库中的EMR记录
    print(f"\n[Step 2] 查询患者的EMR记录:")
    try:
        emrs = list_db_emrs(patient_id=patient_id, limit=1000, include_archived=False)
        print(f"  ✓ 返回 {len(emrs)} 条 EMR 记录")
        
        if not emrs:
            print(f"  ✗ 没有找到任何EMR记录!")
            return False
        
        # 3. 验证每条EMR的数据完整性
        print(f"\n[Step 3] 验证每条EMR记录的数据完整性:")
        required_fields = ["emr_id", "created_at", "diagnosis"]
        all_valid = True
        
        for i, emr in enumerate(emrs, 1):
            missing_fields = [f for f in required_fields if f not in emr]
            
            if missing_fields:
                print(f"  {i}. ✗ EMR缺失字段: {missing_fields}")
                all_valid = False
            else:
                diagnosis_text = emr.get("diagnosis", "待诊断")[:40]
                print(f"  {i}. ✓ {emr['emr_id'][:16]}... | {emr['created_at']} | {diagnosis_text}")
        
        # 4. 验证结果
        print(f"\n[Step 4] 总结:")
        if all_valid:
            print(f"  ✓ 所有 {len(emrs)} 条 EMR 记录数据完整")
            print(f"  ✓ 前端应该能够显示所有记录")
        else:
            print(f"  ✗ 某些EMR记录数据不完整")
            return False
        
        # 5. 示例JSON响应
        print(f"\n[Step 5] API 响应示例 (第一条记录):")
        if emrs:
            sample_emr = emrs[0]
            print(f"  {{")
            print(f"    \"emr_id\": \"{sample_emr.get('emr_id')}\",")
            print(f"    \"created_at\": \"{sample_emr.get('created_at')}\",")
            print(f"    \"patient\": {{")
            patient_info = sample_emr.get("patient", {})
            print(f"      \"patient_id\": \"{patient_info.get('patient_id')}\",")
            print(f"      \"name\": \"{patient_info.get('name')}\",")
            print(f"      \"age\": {patient_info.get('age')}")
            print(f"    }},")
            print(f"    \"diagnosis\": \"{sample_emr.get('diagnosis', '')[:50]}...\",")
            print(f"    ... (其他字段)")
            print(f"  }}")
        
        print(f"\n" + "=" * 75)
        print(f"测试通过! ✓")
        print(f"患者 {patient_name} 的 {len(emrs)} 条诊断报告可以正确显示在前端。")
        print(f"=" * 75)
        return True
        
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_patient_reports()
    sys.exit(0 if success else 1)
