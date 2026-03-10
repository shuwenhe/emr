#!/usr/bin/env python3
"""使用 HTTP 接口直接创建 ClickHouse 表"""

import requests
import json
from typing import Optional
import sys

# ClickHouse 配置
CLICKHOUSE_HOST = "127.0.0.1"
CLICKHOUSE_PORT = 8123  # HTTP 接口端口
CLICKHOUSE_USER = "hospital"
CLICKHOUSE_PASSWORD = "hospital"
CLICKHOUSE_DB = "hospital"

def execute_sql(sql: str, database: Optional[str] = None) -> bool:
    """使用 HTTP 接口执行 SQL"""
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/"
    
    params = {
        "user": CLICKHOUSE_USER,
        "password": CLICKHOUSE_PASSWORD,
    }
    
    if database:
        params["database"] = database
    
    try:
        response = requests.post(
            url,
            params=params,
            data=sql,
            timeout=10
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"✗ SQL 执行失败 (状态码: {response.status_code}): {response.text}")
            return False
    
    except requests.exceptions.ConnectionError:
        print(f"✗ 无法连接到 ClickHouse HTTP 接口")
        print(f"  地址: http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}")
        print(f"  请确保 ClickHouse 正在运行，HTTP 端口为 {CLICKHOUSE_PORT}")
        return False
    except Exception as e:
        print(f"✗ 请求失败: {e}")
        return False

def init_clickhouse() -> bool:
    """初始化 ClickHouse 数据库和表"""
    
    print("=" * 60)
    print("初始化 ClickHouse")
    print("=" * 60)
    
    # 创建数据库
    print(f"\n1. 创建数据库 '{CLICKHOUSE_DB}'...")
    create_db_sql = f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DB}"
    if not execute_sql(create_db_sql):
        return False
    print(f"✓ 数据库 '{CLICKHOUSE_DB}' 已创建（或已存在）")
    
    # 创建表
    print(f"\n2. 创建表 'thermal_timeseries'...")
    create_table_sql = f"""CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DB}.thermal_timeseries (record_id String, device_id String, patient_id String, capture_time DateTime, frame_id String, row UInt16, col UInt16, temperature_c Float32, ingest_time DateTime DEFAULT now()) ENGINE = MergeTree ORDER BY (record_id, frame_id, row, col) PARTITION BY toYYYYMM(capture_time)"""
    
    if not execute_sql(create_table_sql, CLICKHOUSE_DB):
        return False
    print(f"✓ 表 'thermal_timeseries' 已创建（或已存在）")
    
    # 验证表
    print(f"\n3. 验证表结构...")
    check_sql = f"DESCRIBE TABLE {CLICKHOUSE_DB}.thermal_timeseries"
    if not execute_sql(check_sql, CLICKHOUSE_DB):
        print("⚠ 警告：无法验证表结构，但表可能已创建")
        return True
    
    print(f"✓ 表结构验证成功")
    return True

if __name__ == "__main__":
    try:
        import requests
    except ImportError:
        print("✗ 未安装 requests，请运行: pip install requests")
        sys.exit(1)
    
    success = init_clickhouse()
    
    if success:
        print("\n" + "=" * 60)
        print("✓ ClickHouse 初始化完成！")
        print("=" * 60)
        print("\n提示: 如需同步数据，请运行 sync_to_clickhouse.py")
        sys.exit(0)
    else:
        print("\n✗ 初始化失败")
        sys.exit(1)
