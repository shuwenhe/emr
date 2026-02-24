#!/usr/bin/env python3
"""
为所有已有的EMR记录批量生成DOCX报告文件
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import get_db_connection
from app.emr import generate_emr
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """批量为已有EMR记录生成DOCX文件"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 获取所有EMR记录
        cursor.execute("""
            SELECT emr_id, record_id, patient_id, created_at
            FROM emr
            ORDER BY created_at DESC
        """)
        emr_records = cursor.fetchall()
        
        logger.info(f"找到 {len(emr_records)} 条EMR记录")
        
        success_count = 0
        fail_count = 0
        
        for record in emr_records:
            emr_id = record['emr_id']
            record_id = record['record_id']
            patient_id = record['patient_id']
            created_at = record['created_at']
            
            try:
                logger.info(f"为EMR {emr_id} (patient: {patient_id}, record: {record_id}) 重新生成报告...")
                result = generate_emr(record_id)
                logger.info(f"✓ 成功生成 EMR {emr_id} 的报告文件")
                success_count += 1
            except Exception as exc:
                logger.error(f"✗ EMR {emr_id} 生成失败: {exc}")
                fail_count += 1
        
        logger.info(f"\n批量生成完成:")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {fail_count}")
        logger.info(f"  总计: {len(emr_records)}")
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
