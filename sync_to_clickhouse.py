#!/usr/bin/env python3
"""初始化 ClickHouse 数据库和表，并从 MySQL 同步数据"""

import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import sys

try:
    from clickhouse_driver import Client
except ImportError:
    print("✗ 未安装 clickhouse-driver，请运行: pip install clickhouse-driver pymysql")
    sys.exit(1)

try:
    import pymysql
except ImportError:
    print("✗ 未安装 pymysql，请运行: pip install pymysql")
    sys.exit(1)

# ClickHouse 配置
CLICKHOUSE_CONFIG = {
    "host": "127.0.0.1",
    "port": 9000,
    "user": "hospital",
    "password": "hospital",
    "database": "hospital",
}

# MySQL 配置
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "hospital",
    "password": "hospital",
    "database": "hospital",
    "charset": "utf8mb4",
}

def init_clickhouse():
    """初始化 ClickHouse 数据库和表"""
    try:
        # 连接到 ClickHouse（使用 default 数据库）
        admin_client = Client(
            host=CLICKHOUSE_CONFIG["host"],
            port=CLICKHOUSE_CONFIG["port"],
            user=CLICKHOUSE_CONFIG["user"],
            password=CLICKHOUSE_CONFIG["password"],
            database="default"
        )
        
        print("✓ 连接到 ClickHouse")
        
        # 创建数据库
        admin_client.execute(f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_CONFIG['database']}")
        print(f"✓ 数据库 '{CLICKHOUSE_CONFIG['database']}' 已创建（或已存在）")
        
        # 连接到新数据库
        client = Client(
            host=CLICKHOUSE_CONFIG["host"],
            port=CLICKHOUSE_CONFIG["port"],
            user=CLICKHOUSE_CONFIG["user"],
            password=CLICKHOUSE_CONFIG["password"],
            database=CLICKHOUSE_CONFIG["database"]
        )
        
        # 创建表
        client.execute("""
            CREATE TABLE IF NOT EXISTS thermal_timeseries (
                record_id String COMMENT '采集记录ID',
                device_id String COMMENT '设备ID',
                patient_id String COMMENT '患者ID',
                capture_time DateTime COMMENT '采集时间',
                frame_id String COMMENT '帧ID',
                row UInt16 COMMENT '行坐标',
                col UInt16 COMMENT '列坐标',
                temperature_c Float32 COMMENT '温度值（摄氏度）',
                ingest_time DateTime DEFAULT now() COMMENT '数据入库时间'
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(capture_time)
            ORDER BY (record_id, frame_id, row, col)
            COMMENT '热成像时间序列数据表'
        """)
        print("✓ 表 'thermal_timeseries' 已创建（或已存在）")
        
        return True
        
    except Exception as e:
        print(f"✗ ClickHouse 初始化失败: {e}")
        print("  请确保 ClickHouse 服务器正在运行:")
        print("  - 主机: 127.0.0.1")
        print("  - 端口: 9000")
        print("  - 用户: hospital")
        print("  - 密码: hospital")
        return False

def sync_data_from_mysql_files():
    """从 MySQL 中读取记录，并从对应的数据文件中同步时序数据到 ClickHouse"""
    try:
        # 连接到 MySQL
        mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        mysql_cursor = mysql_conn.cursor(pymysql.cursors.DictCursor)
        
        # 连接到 ClickHouse
        ch_client = Client(
            host=CLICKHOUSE_CONFIG["host"],
            port=CLICKHOUSE_CONFIG["port"],
            user=CLICKHOUSE_CONFIG["user"],
            password=CLICKHOUSE_CONFIG["password"],
            database=CLICKHOUSE_CONFIG["database"]
        )
        
        # 获取所有记录
        mysql_cursor.execute("SELECT record_id, patient_id, data_path, metadata_json FROM records")
        records = mysql_cursor.fetchall()
        
        if not records:
            print("ℹ 没有要同步的记录")
            return True
        
        print(f"ℹ 找到 {len(records)} 条记录，开始同步...")
        
        batch_size = 10000
        total_rows = 0
        
        for record in records:
            record_id = record.get("record_id")
            patient_id = record.get("patient_id", "")
            data_path = record.get("data_path")
            metadata_str = record.get("metadata_json", "{}")
            
            try:
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
            except:
                metadata = {}
            
            # 提取设备ID
            device_info = metadata.get("device", {})
            device_id = device_info.get("device_id", "") if isinstance(device_info, dict) else ""
            
            # 解析采集时间
            capture_info = metadata.get("capture", {})
            capture_time_str = capture_info.get("capture_time", "") if isinstance(capture_info, dict) else ""
            
            try:
                capture_time = datetime.fromisoformat(capture_time_str)
            except:
                capture_time = datetime.now()
            
            # 从数据文件读取热成像数据
            if data_path and Path(data_path).exists():
                try:
                    rows_inserted = _insert_from_csv(
                        ch_client, 
                        record_id, 
                        device_id, 
                        patient_id, 
                        capture_time,
                        data_path
                    )
                    total_rows += rows_inserted
                    print(f"  ✓ 记录 {record_id}: 插入 {rows_inserted} 行")
                except Exception as e:
                    print(f"  ✗ 记录 {record_id} 处理失败: {e}")
        
        mysql_cursor.close()
        mysql_conn.close()
        
        print(f"\n✓ 同步完成！共插入 {total_rows} 行数据")
        return True
        
    except Exception as e:
        print(f"✗ 数据同步失败: {e}")
        return False

def _insert_from_csv(client: Client, record_id: str, device_id: str, patient_id: str, 
                      capture_time: datetime, data_path: str) -> int:
    """从 CSV 文件读取热成像数据并插入到 ClickHouse"""
    rows = []
    frame_id = Path(data_path).stem
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # 假设 CSV 格式: row, col, temperature_c
                    row_idx = int(row.get('row', 0))
                    col_idx = int(row.get('col', 0))
                    temp_c = float(row.get('temperature_c', 0.0))
                    
                    rows.append({
                        'record_id': record_id,
                        'device_id': device_id,
                        'patient_id': patient_id,
                        'capture_time': capture_time,
                        'frame_id': frame_id,
                        'row': row_idx,
                        'col': col_idx,
                        'temperature_c': temp_c,
                    })
                except (ValueError, KeyError):
                    continue
        
        if rows:
            client.insert('thermal_timeseries', rows)
        
        return len(rows)
    
    except Exception as e:
        raise Exception(f"Failed to read CSV {data_path}: {e}")

def main():
    """主函数"""
    print("=" * 60)
    print("ClickHouse 数据库初始化和数据同步")
    print("=" * 60)
    
    # 初始化 ClickHouse
    if not init_clickhouse():
        return False
    
    print()
    
    # 同步数据
    if not sync_data_from_mysql_files():
        return False
    
    print("\n✓ 所有操作完成！")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
