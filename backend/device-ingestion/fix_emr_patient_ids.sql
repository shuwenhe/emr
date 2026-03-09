-- 修复EMR记录中缺失的patient_id
-- 通过患者姓名匹配，将EMR记录关联到正确的患者ID

-- 查看需要修复的记录（预览）
SELECT 
    e.emr_id,
    e.patient_id as current_patient_id,
    JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) as patient_name,
    p.patient_id as matched_patient_id,
    e.created_at
FROM emrs e
LEFT JOIN patients p ON JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) = p.name
WHERE e.patient_id IS NULL 
AND JSON_EXTRACT(e.emr_json, '$.patient.name') IS NOT NULL
ORDER BY e.created_at DESC;

-- 统计信息
SELECT 
    'Total NULL patient_id with name' as description,
    COUNT(*) as count
FROM emrs 
WHERE patient_id IS NULL 
AND JSON_EXTRACT(emr_json, '$.patient.name') IS NOT NULL

UNION ALL

SELECT 
    'Can be matched to existing patients' as description,
    COUNT(*) as count
FROM emrs e
INNER JOIN patients p ON JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) = p.name
WHERE e.patient_id IS NULL;

-- 批量修复：更新所有可以匹配的记录
-- 取消下面的注释以执行更新
/*
UPDATE emrs e
INNER JOIN patients p ON JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) = p.name
SET e.patient_id = p.patient_id
WHERE e.patient_id IS NULL 
AND JSON_EXTRACT(e.emr_json, '$.patient.name') IS NOT NULL;

-- 验证修复结果
SELECT 
    'Fixed records' as status,
    COUNT(*) as count 
FROM emrs 
WHERE patient_id IS NOT NULL;

SELECT 
    'Still NULL patient_id' as status,
    COUNT(*) as count 
FROM emrs 
WHERE patient_id IS NULL;
*/
