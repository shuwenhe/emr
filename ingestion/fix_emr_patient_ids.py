#!/usr/bin/env python3
"""
修复EMR记录中缺失的patient_id

问题：历史数据导入时，部分EMR记录的patient_id字段为NULL，
但emr_json中包含患者姓名信息。此脚本通过姓名匹配将这些记录
关联到正确的患者ID。

使用方法:
    python3 fix_emr_patient_ids.py [--dry-run]
    
选项:
    --dry-run  只显示需要修复的记录，不实际更新数据库
"""

import sys
import json
import argparse
from typing import Dict, List, Tuple

# Add current directory to path for imports
sys.path.insert(0, '.')

import pymysql
from app.config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB


def get_connection():
    """创建数据库连接"""
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,  # 使用事务
    )


def get_patients_by_name(conn) -> Dict[str, str]:
    """获取所有患者的姓名到ID的映射"""
    with conn.cursor() as cursor:
        cursor.execute("SELECT patient_id, name FROM patients WHERE name IS NOT NULL AND name != ''")
        rows = cursor.fetchall()
    
    name_to_id = {}
    for row in rows:
        name = row['name'].strip()
        if name:
            name_to_id[name] = row['patient_id']
    
    return name_to_id


def find_emrs_with_null_patient_id(conn) -> List[Dict]:
    """查找patient_id为NULL但emr_json中包含患者姓名的记录"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 
                emr_id,
                patient_id,
                JSON_EXTRACT(emr_json, '$.patient.name') as patient_name,
                JSON_EXTRACT(emr_json, '$.patient.patient_id') as json_patient_id,
                created_at
            FROM emrs 
            WHERE patient_id IS NULL 
            AND JSON_EXTRACT(emr_json, '$.patient.name') IS NOT NULL
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
    
    results = []
    for row in rows:
        # 清理JSON字符串中的引号
        patient_name = row.get('patient_name')
        if patient_name:
            patient_name = patient_name.strip('"')
        
        json_patient_id = row.get('json_patient_id')
        if json_patient_id:
            json_patient_id = json_patient_id.strip('"')
        
        results.append({
            'emr_id': row['emr_id'],
            'patient_name': patient_name,
            'json_patient_id': json_patient_id,
            'created_at': row['created_at']
        })
    
    return results


def match_and_fix(conn, emrs: List[Dict], name_to_id: Dict[str, str], dry_run: bool = False) -> Tuple[int, int]:
    """匹配EMR记录到患者并更新patient_id
    
    Returns:
        (matched_count, updated_count) 匹配数量和更新数量
    """
    matched = []
    unmatched = []
    
    for emr in emrs:
        patient_name = emr['patient_name']
        json_patient_id = emr['json_patient_id']
        
        # 优先使用emr_json中的patient_id
        matched_patient_id = None
        if json_patient_id and json_patient_id in name_to_id.values():
            matched_patient_id = json_patient_id
        elif patient_name and patient_name in name_to_id:
            matched_patient_id = name_to_id[patient_name]
        
        if matched_patient_id:
            matched.append({
                'emr_id': emr['emr_id'],
                'patient_id': matched_patient_id,
                'patient_name': patient_name,
                'created_at': emr['created_at']
            })
        else:
            unmatched.append(emr)
    
    print(f"\n找到 {len(matched)} 条可匹配的EMR记录")
    print(f"无法匹配 {len(unmatched)} 条记录\n")
    
    if matched:
        print("可匹配的记录:")
        print("-" * 80)
        for record in matched:
            print(f"  EMR ID: {record['emr_id']}")
            print(f"  患者: {record['patient_name']} (ID: {record['patient_id']})")
            print(f"  创建时间: {record['created_at']}")
            print()
    
    if unmatched:
        print("\n无法匹配的记录 (患者不存在或姓名无法匹配):")
        print("-" * 80)
        for record in unmatched:
            print(f"  EMR ID: {record['emr_id']}")
            print(f"  患者姓名: {record['patient_name']}")
            print(f"  JSON中的patient_id: {record.get('json_patient_id', 'N/A')}")
            print()
    
    updated_count = 0
    if not dry_run and matched:
        print(f"\n开始更新 {len(matched)} 条记录...")
        try:
            with conn.cursor() as cursor:
                for record in matched:
                    cursor.execute(
                        "UPDATE emrs SET patient_id = %s WHERE emr_id = %s",
                        (record['patient_id'], record['emr_id'])
                    )
                    updated_count += 1
            
            conn.commit()
            print(f"✓ 成功更新 {updated_count} 条记录")
        except Exception as e:
            conn.rollback()
            print(f"✗ 更新失败: {e}")
            raise
    elif dry_run and matched:
        print(f"\n[DRY RUN] 将更新 {len(matched)} 条记录 (使用 --dry-run 参数时不会实际更新)")
    
    return len(matched), updated_count


def main():
    parser = argparse.ArgumentParser(description="修复EMR记录中缺失的patient_id")
    parser.add_argument('--dry-run', action='store_true', help='只显示需要修复的记录，不实际更新')
    args = parser.parse_args()
    
    print("EMR Patient ID 修复工具")
    print("=" * 80)
    
    conn = get_connection()
    try:
        # 1. 获取患者姓名到ID的映射
        print("\n步骤 1: 加载患者数据...")
        name_to_id = get_patients_by_name(conn)
        print(f"找到 {len(name_to_id)} 个患者")
        
        # 2. 查找需要修复的EMR记录
        print("\n步骤 2: 查找需要修复的EMR记录...")
        emrs = find_emrs_with_null_patient_id(conn)
        print(f"找到 {len(emrs)} 条patient_id为NULL的EMR记录")
        
        if not emrs:
            print("\n✓ 所有EMR记录的patient_id都已正确设置，无需修复")
            return
        
        # 3. 匹配并修复
        print("\n步骤 3: 匹配患者并更新...")
        matched_count, updated_count = match_and_fix(conn, emrs, name_to_id, dry_run=args.dry_run)
        
        print("\n" + "=" * 80)
        print("修复完成")
        print(f"  匹配成功: {matched_count} 条")
        print(f"  实际更新: {updated_count} 条")
        
        if args.dry_run:
            print("\n提示: 运行时不加 --dry-run 参数即可实际更新数据库")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
