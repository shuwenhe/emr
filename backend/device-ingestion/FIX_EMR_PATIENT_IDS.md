# EMR Patient ID 修复说明

## 问题描述

在历史数据导入过程中，部分EMR记录的 `patient_id` 字段未正确设置（为NULL），但这些记录的 `emr_json` 字段中包含患者的姓名信息。这导致：

- 疗效对比页面查询不到该患者的诊断报告
- 患者数据分析页面无法显示完整病历

## 已修复的患者

- ✅ **冯加仑** (P036A91B77191) - 2条EMR记录已关联

## 快速修复方法

### 方法1: 使用SQL脚本（推荐）

```bash
# 1. 预览需要修复的记录
mysql -u hospital -phospital hospital < fix_emr_patient_ids.sql | head -50

# 2. 执行修复（取消SQL文件中UPDATE语句的注释）
# 编辑 fix_emr_patient_ids.sql，取消最后的 UPDATE 语句注释
mysql -u hospital -phospital hospital < fix_emr_patient_ids.sql
```

### 方法2: 直接SQL命令

```bash
# 批量修复所有可匹配的记录
mysql -u hospital -phospital hospital << 'EOF'
UPDATE emrs e
INNER JOIN patients p ON JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) = p.name
SET e.patient_id = p.patient_id
WHERE e.patient_id IS NULL 
AND JSON_EXTRACT(e.emr_json, '$.patient.name') IS NOT NULL;

SELECT CONCAT('✓ 已修复 ', ROW_COUNT(), ' 条EMR记录') as result;
EOF
```

### 方法3: 逐个修复特定患者

```bash
# 查找特定患者的EMR记录
mysql -u hospital -phospital hospital -e "
SELECT 
    emr_id,
    JSON_UNQUOTE(JSON_EXTRACT(emr_json, '$.patient.name')) as name
FROM emrs 
WHERE patient_id IS NULL 
AND JSON_EXTRACT(emr_json, '$.patient.name') LIKE '%患者姓名%';
"

# 手动更新（替换emr_id和patient_id）
mysql -u hospital -phospital hospital -e "
UPDATE emrs 
SET patient_id = 'P036A91B77191' 
WHERE emr_id = 'EMR-xxxxx';
"
```

## 验证修复结果

```bash
# 检查冯加仑的记录
curl -s "http://localhost:8000/emr?patient_id=P036A91B77191" | python3 -m json.tool | head -50

# 或使用MySQL查询
mysql -u hospital -phospital hospital -e "
SELECT COUNT(*) as record_count 
FROM emrs 
WHERE patient_id = 'P036A91B77191';
"
```

## 预防措施

### 修改save_emr函数确保patient_id正确设置

在 `app/emr.py` 中的生成EMR逻辑应该始终确保：

```python
emr = {
    "emr_id": emr_id,
    "patient": {
        "patient_id": patient_id,  # ✓ 必须设置
        "name": patient_name,
        # ...
    },
    # ...
}
```

### 数据导入时的检查

在历史数据导入功能中添加验证：

```python
def import_historical_record(record_data):
    patient = record_data.get('patient', {})
    if not patient.get('patient_id'):
        # 通过姓名查找或创建患者
        patient_id = find_or_create_patient(patient)
        patient['patient_id'] = patient_id
    
    # 确保EMR记录正确关联患者
    emr = generate_emr_from_record(record_data)
    assert emr.get('patient', {}).get('patient_id'), "Patient ID must be set"
```

## 数据统计

当前数据库状态：

```sql
-- 总EMR记录数
SELECT COUNT(*) as total FROM emrs;

-- 有patient_id的记录
SELECT COUNT(*) as with_id FROM emrs WHERE patient_id IS NOT NULL;

-- patient_id为NULL的记录
SELECT COUNT(*) as null_id FROM emrs WHERE patient_id IS NULL;

-- 可通过姓名匹配的记录
SELECT COUNT(*) as matchable
FROM emrs e
INNER JOIN patients p ON JSON_UNQUOTE(JSON_EXTRACT(e.emr_json, '$.patient.name')) = p.name
WHERE e.patient_id IS NULL;
```

## 常见问题

### Q: 修复后前端还是看不到记录？
A: 刷新浏览器页面，清除缓存。API会立即返回更新后的数据。

### Q: 有些记录无法匹配怎么办？
A: 这些记录可能是测试数据或患者尚未在系统中注册。可以：
1. 先在"患者登记"页面添加患者
2. 手动更新EMR记录关联患者ID
3. 或标记为archived归档

### Q: 如何避免将来出现这个问题？
A: 
1. 确保所有数据上传/导入流程都正确设置patient_id
2. 在save_emr()函数中添加断言检查
3. 定期运行检查脚本验证数据完整性
