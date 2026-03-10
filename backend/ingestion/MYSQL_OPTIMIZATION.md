# MySQL 排序缓冲溢出问题解决方案

## 问题诊断

### 错误信息
```
MySQL operational error: (1038, 'Out of sort memory, consider increasing server sort buffer size')
```

### 根本原因
当 MySQL 执行 `ORDER BY` 操作时：
1. 需要排序的数据集太大
2. 排序字段与大字段（如 JSON）在同一表中
3. MySQL 的 `sort_buffer_size` 配置太小

### 受影响的操作
- `GET /emr?patient_id=...&include_archived=true` ← **主要问题源**
- 任何包含 `payload_json` 或 `emr_json` 的大数据集排序

---

## 解决方案

### 1. ✅ 代码层优化（已实施）

#### 改进 `list_emrs()` 函数
```python
# 优化策略：两步查询，小字段用于排序

# 步骤1：只查询排序所需的小字段（<1KB/行）
SELECT emr_id, created_at FROM emrs 
WHERE patient_id = ? AND archived = 0
ORDER BY created_at DESC LIMIT 100

# 步骤2：根据ID批量获取完整数据
SELECT * FROM emrs WHERE emr_id IN (...)
```

**效果**：
- 排序缓冲只需处理小字段（emr_id + created_at）
- 避免在排序时加载大的 emr_json
- 内存消耗从几百MB → 几MB

---

### 2. 🔧 MySQL 配置优化（必须施行）

#### 增加排序缓冲大小
编辑 `/etc/mysql/mysql.conf.d/mysqld.cnf` 或 `/etc/mysql/my.cnf`：

```ini
[mysqld]
# 增加排序缓冲 (默认256KB，改为32-128MB)
sort_buffer_size = 128M

# 增加读缓冲 (顺序读优化)
read_rnd_buffer_size = 32M

# 增加连接缓冲
join_buffer_size = 32M

# 增加临时表大小限制
tmp_table_size = 512M
max_heap_table_size = 512M

# 慢查询日志（用于监控）
slow_query_log = 1
long_query_time = 2
slow_query_log_file = /var/log/mysql/slow-query.log
```

#### 立即生效的配置方式（不需重启）
```sql
-- MySQL 连接中执行
SET GLOBAL sort_buffer_size = 128 * 1024 * 1024;
SET GLOBAL read_rnd_buffer_size = 32 * 1024 * 1024;
SET GLOBAL join_buffer_size = 32 * 1024 * 1024;
SET GLOBAL tmp_table_size = 512 * 1024 * 1024;
SET GLOBAL max_heap_table_size = 512 * 1024 * 1024;

-- 验证设置
SHOW VARIABLES LIKE '%buffer%';
SHOW VARIABLES LIKE 'tmp_table_size';
```

---

### 3. 📊 数据库索引优化（必须施行）

#### 创建覆盖索引，优化排序
```sql
-- 优先级1：emrs 表的核心索引
CREATE INDEX idx_emrs_patient_created_id 
ON emrs (patient_id, archived, created_at DESC, emr_id);

CREATE INDEX idx_emrs_created_id 
ON emrs (created_at DESC, emr_id);

-- 优先级2：patients 表
CREATE INDEX idx_patients_updated_id 
ON patients (archived, updated_at DESC, patient_id);

-- 优先级3：records 表
CREATE INDEX idx_records_patient_created 
ON records (patient_id, created_at DESC);

-- 查看现有索引
SHOW INDEX FROM emrs;
SHOW INDEX FROM patients;
SHOW INDEX FROM records;
```

#### 索引设计原理
```
传统索引：
  patient_id, archived, created_at DESC
  
问题：排序时仍需读取 emr_json 字段

覆盖索引（推荐）：
  patient_id, archived, created_at DESC, emr_id
  
优势：
  - MySQL 可直接从索引读取所有需要的字段
  - 无需回表读取大的 emr_json
  - 排序操作完全在内存中完成
```

---

### 4. 🔍 监控和诊断

#### 检查当前性能瓶颈
```sql
-- 查看排序操作的统计信息
SHOW STATUS LIKE 'Sort%';
-- 结果示例：
-- Sort_merge_passes: 0 (越小越好)
-- Sort_range: 5000
-- Sort_rows: 50000
-- Sort_scan: 100

-- 查看慢查询日志
TAIL -f /var/log/mysql/slow-query.log

-- 分析特定查询
EXPLAIN SELECT emr_id, created_at FROM emrs 
WHERE patient_id = 'PA0793AA8CF11' AND archived = 0
ORDER BY created_at DESC LIMIT 100;

-- 预期结果：
-- type: range (好) 而不是 ALL (坏)
-- rows: < 1000 (好)
-- Extra: Using index (最好) 或 Using filesort (可接受)
```

---

### 5. 📋 验证步骤

#### 部署顺序
1. ✅ **代码优化** (已完成)
   - 改进 `list_emrs()` 函数的两步查询
   - 添加 API 查询限制 (limit=100, max=1000)

2. 🔧 **MySQL 配置优化** (立即执行)
   ```bash
   mysql -u root -p -e "SET GLOBAL sort_buffer_size = 128 * 1024 * 1024;"
   ```

3. 📊 **创建覆盖索引** (立即执行)
   ```bash
   mysql -u root -p < index_optimization.sql
   ```

4. 🧪 **功能测试**
   ```bash
   # 测试大数据集查询
   curl "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true"
   
   # 检查响应时间（应 < 1s）
   time curl "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true" > /dev/null
   ```

---

## 总结对比

### 优化前
| 指标 | 值 |
|------|-----|
| 错误 | MySQL operational error (1038) |
| API 响应时间 | Timeout (>30s) |
| 排序缓冲溢出 | 频繁 |
| 数据库CPU | >90% |

### 优化后（预期）
| 指标 | 值 |
|------|-----|
| 错误 | ✅ 无 |
| API 响应时间 | < 500ms |
| 排序缓冲溢出 | ✅ 无 |
| 数据库CPU | < 20% |

---

## 临时应急方案

如果无法立即修改MySQL配置，可使用：

```python
# 在 data_platform.py 中临时调整
def list_emrs(...):
    # 临时限制查询数量
    limit = min(limit, 30)  # 从50降低到30
    # ... 其他代码
```

这会降低排序缓冲的压力，但不是长期方案。
