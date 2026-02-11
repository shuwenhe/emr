-- 初始化 MySQL 数据库与用户
CREATE DATABASE IF NOT EXISTS hospital DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'hospital'@'%' IDENTIFIED BY 'hospital';

GRANT ALL PRIVILEGES ON hospital.* TO 'hospital'@'%';

FLUSH PRIVILEGES;
