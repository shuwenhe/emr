-- 初始化 MySQL 数据库与用户
CREATE DATABASE IF NOT EXISTS hospital DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE hospital;

CREATE USER IF NOT EXISTS 'hospital'@'%' IDENTIFIED BY 'hospital';

GRANT ALL PRIVILEGES ON hospital.* TO 'hospital'@'%';

FLUSH PRIVILEGES;

-- 患者表
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='患者信息表';

-- 采集记录表
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集记录表';

-- 报告表
CREATE TABLE IF NOT EXISTS reports (
    record_id VARCHAR(64) PRIMARY KEY COMMENT '采集记录ID',
    report_json JSON COMMENT '报告JSON',
    created_at DATETIME COMMENT '创建时间',
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分析报告表';

-- 治疗计划表
CREATE TABLE IF NOT EXISTS plans (
    record_id VARCHAR(64) PRIMARY KEY COMMENT '采集记录ID',
    plan_json JSON COMMENT '治疗计划JSON',
    created_at DATETIME COMMENT '创建时间',
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='治疗计划表';

-- 电子病历表
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电子病历表';
