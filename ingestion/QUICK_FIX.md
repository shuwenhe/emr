# 🚀 快速修复指南 - MySQL 排序缓冲溢出问题

## 问题回顾

```
错误: MySQL operational error (1038) 'Out of sort memory, consider increasing server sort buffer size'
影响: 查询患者EMR列表时超时
症状: include_archived=true 时特别明显
```

---

## 立即执行步骤

### ✅ 步骤1：验证代码已优化（已完成）

查看文件修改：
```bash
# 已优化的文件
- app/main.py          ✅ list_emr_endpoint 已改进
- app/data_platform.py ✅ list_emrs() 已改为两步查询
```

---

### 🔧 步骤2：优化 MySQL（必须执行）

#### 快速临时修复（立即生效，不需重启）
```bash
# 在有 MySQL 访问权限的服务器上执行
cd /home/shuwen/emr/ingestion

# 方式1：使用 SQL 脚本
mysql -u <用户名> -p < mysql_optimization.sql

# 方式2：手动执行（输入密码后逐行执行）
mysql -u <用户名> -p << 'EOF'
SET GLOBAL sort_buffer_size = 128 * 1024 * 1024;
SET GLOBAL read_rnd_buffer_size = 32 * 1024 * 1024;
SET GLOBAL join_buffer_size = 32 * 1024 * 1024;
SET GLOBAL tmp_table_size = 512 * 1024 * 1024;
SET GLOBAL max_heap_table_size = 512 * 1024 * 1024;
EOF
```

#### 创建优化索引
```bash
# 继续在 MySQL 中执行
mysql -u <用户名> -p < mysql_optimization.sql
```

#### 永久生效（需要重启 MySQL）
```bash
# 编辑 MySQL 配置文件
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

# 在 [mysqld] 段下添加
sort_buffer_size = 128M
read_rnd_buffer_size = 32M
join_buffer_size = 32M
tmp_table_size = 512M
max_heap_table_size = 512M

# 保存后重启 MySQL
sudo systemctl restart mysql
```

---

### 🧪 步骤3：验证修复效果

```bash
# 测试 API 端点（替换为实际的patient_id）
curl -X GET "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true" \
  -H "Accept: application/json" \
  -w "\n耗时: %{time_total}s\n"

# 预期结果：
# - 状态码: 200 (不是 503)
# - 耗时: < 1s (不是超时)
# - 数据: 返回 EMR 列表
```

---

### 📊 查看改进指标

```bash
# 连接 MySQL 查看配置
mysql -u <用户名> -p -e "SHOW VARIABLES LIKE 'sort_buffer_size';"

# 查看索引是否创建成功
mysql -u <用户名> -p -e "SHOW INDEX FROM emrs;"
```

---

## 如果问题仍然存在

### 诊断步骤

```bash
# 1. 查看 MySQL 错误日志
tail -100 /var/log/mysql/error.log

# 2. 查看慢查询日志（如果启用）
tail -50 /var/log/mysql/slow-query.log

# 3. 查看当前缓冲大小（验证修改是否生效）
mysql -u <用户名> -p -e "SHOW VARIABLES LIKE '%buffer%';"

# 4. 分析具体查询的执行计划
mysql -u <用户名> -p << 'EOF'
EXPLAIN SELECT emr_id, created_at FROM emrs 
WHERE patient_id = 'PA0793AA8CF11' AND archived = 0 
ORDER BY created_at DESC LIMIT 100;
EOF
```

### 常见问题排查

| 问题 | 原因 | 解决方案 |
|------|------|--------|
| `SET GLOBAL` 权限不足 | 非 root 用户 | 使用 `sudo` 或 root 用户执行 |
| 索引创建失败 | 索引已存在 | 忽略警告，继续 |
| 仍然超时 | 数据集太大 | 检查是否需要分区或归档旧数据 |
| 配置重启后丢失 | 未修改配置文件 | 编辑 `/etc/mysql/mysql.conf.d/mysqld.cnf` |

---

## 预期改进

### 修复前
```
GET /emr?patient_id=PA0793AA8CF11&include_archived=true
→ 错误: (1038) Out of sort memory
→ 状态: 503 Service Unavailable
→ 耗时: Timeout
```

### 修复后
```
GET /emr?patient_id=PA0793AA8CF11&include_archived=true
→ 状态: 200 OK
→ 耗时: 200-500ms
→ 数据: [{ emr_id, record_id, ... }, ...]
```

---

## 文有关更多细节

- 📖 [MYSQL_OPTIMIZATION.md](./MYSQL_OPTIMIZATION.md) - 详细技术说明
- 📖 [PERFORMANCE_OPTIMIZATION.md](./PERFORMANCE_OPTIMIZATION.md) - 总体性能优化策略
- 🔨 [mysql_optimization.sql](./mysql_optimization.sql) - SQL 优化脚本

---

## TLDR（三句话总结）

1. 🐍 **Python 代码已修复**：`list_emrs()` 改为两步查询，避免大字段参与排序
2. 🔧 **MySQL 配置需调整**：运行 `mysql_optimization.sql` 脚本增加缓冲大小
3. 📊 **创建覆盖索引**：同一脚本中已包含，加速排序和查询

👉 **现在就执行**：`mysql -u 用户名 -p < mysql_optimization.sql`
