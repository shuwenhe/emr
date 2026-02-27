#!/bin/bash
# ClickHouse initialization script
# This script runs when ClickHouse container starts

set -e

# Wait for ClickHouse to be ready
echo "Waiting for ClickHouse to be ready..."
max_attempts=30
attempt=0
until [ $attempt -ge $max_attempts ]; do
  if clickhouse-client -h localhost --user="${CLICKHOUSE_USER}" --password="${CLICKHOUSE_PASSWORD}" -q "SELECT 1" > /dev/null 2>&1; then
    echo "ClickHouse is ready!"
    break
  fi
  echo "ClickHouse is unavailable - sleeping (attempt $((attempt+1))/$max_attempts)"
  sleep 2
  attempt=$((attempt+1))
done

if [ $attempt -ge $max_attempts ]; then
  echo "ClickHouse failed to start after $max_attempts attempts"
  exit 1
fi

echo "ClickHouse is up, initializing schema..."

# Create database
echo "Creating database: hospital"
clickhouse-client -h localhost \
  --user="${CLICKHOUSE_USER}" \
  --password="${CLICKHOUSE_PASSWORD}" \
  -q "CREATE DATABASE IF NOT EXISTS hospital"

# Create thermal_timeseries table for storing time-series thermal imaging data
echo "Creating table: hospital.thermal_timeseries"
clickhouse-client -h localhost \
  --user="${CLICKHOUSE_USER}" \
  --password="${CLICKHOUSE_PASSWORD}" \
  --database="hospital" \
  -q "
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
  ORDER BY (record_id, frame_id, row, col)
  PARTITION BY toYYYYMM(capture_time)
"

echo "Verifying table structure..."
clickhouse-client -h localhost \
  --user="${CLICKHOUSE_USER}" \
  --password="${CLICKHOUSE_PASSWORD}" \
  --database="hospital" \
  -q "DESCRIBE TABLE thermal_timeseries"

echo "ClickHouse initialization completed successfully!"
