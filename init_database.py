#!/usr/bin/env python3
"""初始化 hospital 数据库表结构"""

import pymysql
import sys

# MySQL 连接配置
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "hospital",
    "password": "hospital",
    "database": "hospital",
    "charset": "utf8mb4",
}

# SQL 创建表语句
SQL_STATEMENTS = [
    # 患者表
    """
    CREATE TABLE IF NOT EXISTS patients (
        patient_id VARCHAR(64) PRIMARY KEY COMMENT '患者ID',
        name VARCHAR(128) COMMENT '患者姓名',
        gender VARCHAR(32) COMMENT '性别',
        age INT COMMENT '年龄',
        archived TINYINT DEFAULT 0 COMMENT '是否归档',
        payload_json JSON COMMENT '患者详细信息JSON',
        updated_at DATETIME COMMENT '更新时间',
        KEY idx_archived (archived),
        KEY idx_updated_at (updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='患者信息表'
    """,
    
    # 采集记录表
    """
    CREATE TABLE IF NOT EXISTS records (
        record_id VARCHAR(64) PRIMARY KEY COMMENT '采集记录ID',
        patient_id VARCHAR(64) COMMENT '患者ID',
        created_at DATETIME COMMENT '创建时间',
        data_path TEXT COMMENT '数据文件路径',
        metadata_json JSON COMMENT '采集元数据',
        image_paths_json JSON COMMENT '图像路径JSON',
        INDEX idx_records_patient (patient_id),
        INDEX idx_created_at (created_at),
        CONSTRAINT fk_records_patient
            FOREIGN KEY (patient_id)
            REFERENCES patients(patient_id)
            ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集记录表'
    """,
    
    # 报告表
    """
    CREATE TABLE IF NOT EXISTS reports (
        record_id VARCHAR(64) PRIMARY KEY COMMENT '采集记录ID',
        report_json JSON COMMENT '报告JSON',
        created_at DATETIME COMMENT '创建时间',
        KEY idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分析报告表'
    """,
    
    # 治疗计划表
    """
    CREATE TABLE IF NOT EXISTS plans (
        record_id VARCHAR(64) PRIMARY KEY COMMENT '采集记录ID',
        plan_json JSON COMMENT '治疗计划JSON',
        created_at DATETIME COMMENT '创建时间',
        KEY idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='治疗计划表'
    """,
    
    # 电子病历表
    """
    CREATE TABLE IF NOT EXISTS emrs (
        emr_id VARCHAR(64) PRIMARY KEY COMMENT '病历ID',
        record_id VARCHAR(64) COMMENT '采集记录ID',
        patient_id VARCHAR(64) COMMENT '患者ID',
        created_at DATETIME COMMENT '创建时间',
        archived TINYINT DEFAULT 0 COMMENT '是否归档',
        emr_json JSON COMMENT '病历JSON',
        KEY idx_emrs_patient (patient_id),
        KEY idx_emrs_record (record_id),
        KEY idx_archived (archived),
        KEY idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电子病历表'
    """
]

def init_database():
    """初始化数据库表"""
    try:
        # 连接到 MySQL
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        
        print("✓ 成功连接到 MySQL 数据库")
        
        # 执行建表语句
        for i, sql in enumerate(SQL_STATEMENTS, 1):
            try:
                cursor.execute(sql)
                table_name = sql.split("CREATE TABLE IF NOT EXISTS")[1].split("(")[0].strip()
                print(f"✓ 表 '{table_name}' 创建成功（或已存在）")
            except Exception as e:
                print(f"✗ 执行第 {i} 个 SQL 失败: {e}")
                return False
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n✓ 数据库初始化完成！")
        return True
        
    except pymysql.Error as e:
        print(f"✗ MySQL 连接错误: {e}")
        print("  请确保 MySQL 服务器正在运行:")
        print("  - 主机: 127.0.0.1")
        print("  - 端口: 3306")
        print("  - 用户: hospital")
        print("  - 密码: hospital")
        return False
    except Exception as e:
        print(f"✗ 未知错误: {e}")
        return False

if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
