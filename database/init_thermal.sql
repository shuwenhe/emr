-- ClickHouse 初始化脚本
-- 创建 hospital 数据库和 thermal_timeseries 表

-- 创建数据库
CREATE DATABASE IF NOT EXISTS hospital;

-- 创建热成像时间序列数据表
CREATE TABLE IF NOT EXISTS hospital.thermal_timeseries (
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
PARTITION BY toYYYYMM(capture_time);
