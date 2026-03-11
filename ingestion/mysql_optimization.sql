-- MySQL 优化索引和配置脚本
-- 执行方式: mysql -u root -p < mysql_optimization.sql

-- ============================================================
-- 1. MySQL 全局配置（SET GLOBAL）
-- ============================================================

SET GLOBAL sort_buffer_size = 128 * 1024 * 1024;           -- 128MB (from 256KB)
SET GLOBAL read_rnd_buffer_size = 32 * 1024 * 1024;        -- 32MB
SET GLOBAL join_buffer_size = 32 * 1024 * 1024;            -- 32MB
SET GLOBAL tmp_table_size = 512 * 1024 * 1024;             -- 512MB
SET GLOBAL max_heap_table_size = 512 * 1024 * 1024;        -- 512MB

-- 验证设置
SHOW VARIABLES LIKE 'sort_buffer_size';
SHOW VARIABLES LIKE 'read_rnd_buffer_size';
SHOW VARIABLES LIKE 'join_buffer_size';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';

-- ============================================================
-- 2. EMRs 表优化索引
-- ============================================================

-- 主要查询索引：patient_id + archived + created_at 排序 + emr_id 覆盖
ALTER TABLE emrs ADD INDEX idx_emrs_patient_created_id 
(patient_id, archived, created_at DESC, emr_id);

-- 辅助查询索引：按 created_at 排序的全表扫描，带 emr_id 覆盖
ALTER TABLE emrs ADD INDEX idx_emrs_created_id 
(created_at DESC, emr_id);

-- record_id 快速查询
ALTER TABLE emrs ADD INDEX idx_emrs_record_id (record_id);

-- 删除旧的不优化的索引（如果存在）
-- ALTER TABLE emrs DROP INDEX idx_emrs_patient_archived_created;

-- 查看 EMRs 表的所有索引
SHOW INDEX FROM emrs;

-- ============================================================
-- 3. Patients 表优化索引
-- ============================================================

-- 主要查询索引：archived + updated_at 排序 + patient_id 覆盖
ALTER TABLE patients ADD INDEX idx_patients_updated_id 
(archived, updated_at DESC, patient_id);

-- 查看 Patients 表的所有索引
SHOW INDEX FROM patients;

-- ============================================================
-- 4. Records 表优化索引
-- ============================================================

-- 患者记录查询索引
ALTER TABLE records ADD INDEX idx_records_patient_created 
(patient_id, created_at DESC);

-- 查看 Records 表的所有索引
SHOW INDEX FROM records;

-- ============================================================
-- 5. 查询性能分析
-- ============================================================

-- 分析主要查询的执行计划
EXPLAIN SELECT emr_id, created_at 
FROM emrs 
WHERE patient_id = 'PA0793AA8CF11' AND archived = 0 
ORDER BY created_at DESC LIMIT 100;

-- 预期结果：
-- type: range 或 index (好)
-- rows: < 1000 (好)
-- Extra: Using index 或 Using where (好) [不应该看到 Using filesort]

-- ============================================================
-- 6. 表统计信息更新（重要）
-- ============================================================

-- 更新表的统计信息，帮助 MySQL 优化器作出更好的决定
ANALYZE TABLE emrs;
ANALYZE TABLE patients;
ANALYZE TABLE records;
ANALYZE TABLE reports;

-- 显示表统计信息
SHOW TABLE STATUS LIKE 'emrs';
SHOW TABLE STATUS LIKE 'patients';

-- ============================================================
-- 7. 监控性能指标
-- ============================================================

-- 查看排序相关的性能计数器
SHOW STATUS LIKE 'Sort%';

-- 预期结果示例：
-- Sort_merge_passes: 0 (合并排序次数，越小越好)
-- Sort_range: 5000
-- Sort_rows: 50000
-- Sort_scan: 100

-- ============================================================
-- 8. 持久化配置（可选，需重启MySQL）
-- ============================================================

-- 在 /etc/mysql/mysql.conf.d/mysqld.cnf 中添加以下内容：
/*
[mysqld]
# 排序缓冲配置
sort_buffer_size = 128M
read_rnd_buffer_size = 32M
join_buffer_size = 32M
tmp_table_size = 512M
max_heap_table_size = 512M

# 慢查询日志
slow_query_log = 1
long_query_time = 2
slow_query_log_file = /var/log/mysql/slow-query.log
log_queries_not_using_indexes = 1
*/

-- ============================================================
-- 完毕
-- ============================================================
