# 完整部署指南 - 解决患者诊断报告查询问题

## 现状分析

### 问题表现
```
❌ 患者页面加载中...
⚠ 未找到诊断报告（正在查询中...）
疗效对比：[加载中]
```

**原因**：
1. ✅ Python代码已优化（消除冗余查询）
2. ⏳ **MySQL配置未优化**（排序缓冲仍然溢出）
3. ⏳ **应用未重启**（新代码未生效）

---

## 🚀 部署步骤（按顺序执行）

### Step 1: 重启 FastAPI 应用（使代码更改生效）

```bash
# 方式1：如果使用 systemd
sudo systemctl restart device-ingestion

# 方式2：如果使用 Docker
docker restart device-ingestion-api

# 方式3：手动停止/启动
pkill -f "uvicorn.*main:app"
sleep 2
cd /home/shuwen/emr/backend/device-ingestion
source /home/shuwen/.venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 方式4：验证应用是否运行
curl http://localhost:8000/platform/summary
# 应返回 {"patients": ..., "records": ..., ...}
```

### Step 2: 执行 MySQL 优化脚本（增加排序缓冲）

```bash
# 切换到项目目录
cd /home/shuwen/emr/backend/device-ingestion

# 执行SQL优化脚本
# 需要MySQL root权限或管理员权限
mysql -u root -p < mysql_optimization.sql

# 如果需要指定host/port
# mysql -h 127.0.0.1 -u root -p -P 3306 < mysql_optimization.sql
```

脚本将：
- ✅ 增加 `sort_buffer_size` 从 256KB 到 128MB
- ✅ 创建覆盖索引加速查询
- ✅ 更新表统计信息

### Step 3: 验证修复效果

```bash
# 测试1：检查MySQL配置是否生效
mysql -u root -p -e "SHOW VARIABLES LIKE 'sort_buffer_size';"
# 预期输出：sort_buffer_size | 134217728 (即128M)

# 测试2：验证索引是否创建
mysql -u root -p -e "SHOW INDEX FROM emrs \G" | grep idx_emrs_patient_created_id
# 预期看到新创建的索引

# 测试3：测试API端点
curl -X GET "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true" \
  -H "Accept: application/json" \
  -w "\n状态码: %{http_code}\n耗时: %{time_total}s\n"

# 预期结果：
# 状态码: 200 (不是503)
# 耗时: 0.3-1.0s
```

### Step 4: 前端刷新验证

在浏览器中刷新患者页面：

```
https://your-app.com/patient/PA0793AA8CF11
```

**预期结果**：
- ✅ 页面快速加载（<2s）
- ✅ 诊断报告正常显示
- ✅ 疗效对比数据显示
- ❌ 不再出现"503 Service Unavailable"

---

## 📊 修复前后对比

### 修复前
```
请求：GET /emr?patient_id=PA0793AA8CF11&include_archived=true
├─ 数据库查询数：4-7次
├─ 排序缓冲消耗：500MB+
├─ MySQL错误：(1038) Out of sort memory
├─ HTTP状态码：503
├─ 响应时间：Timeout (>30s)
└─ 用户体验：❌ 见鬼了，为什么一直在加载...

患者页面: 
├─ 加载状态：⚠ 未找到诊断报告
├─ 疗效对比：[永远加载中]
└─ 时间：2+ 分钟后超时
```

### 修复后（预期）
```
请求：GET /emr?patient_id=PA0793AA8CF11&include_archived=true
├─ 数据库查询数：1次
├─ 排序缓冲消耗：5KB
├─ MySQL错误：无
├─ HTTP状态码：200
├─ 响应时间：300-500ms
└─ 用户体验：✅ 数据秒出

患者页面：
├─ 加载状态：✅ 诊断报告已显示
├─ 疗效对比：✅ 数据已加载
└─ 时间：<2秒完成
```

---

## 🔍 诊断命令（如果仍有问题）

### 检查1：应用是否重启成功
```bash
# 查看应用进程
ps aux | grep uvicorn

# 查看应用日志
tail -100 /var/log/device-ingestion/app.log
# 或
journalctl -u device-ingestion -n 100 -f

# 确认应用未卡在旧代码
curl -X GET "http://localhost:8000/emr?patient_id=test" \
  -o /dev/null -s -w "HTTP %{http_code}\n"
```

### 检查2：MySQL配置是否生效
```bash
# 查看排序缓冲大小
mysql -u root -p -e "SHOW VARIABLES LIKE 'sort_buffer_size';"
# 应显示 134217728 (128M) 而不是 262144 (256K)

# 如果仍是256K，说明配置未生效，需要：
# 1. 确认是否正确执行了SQL脚本
# 2. 检查MySQL是否需要重启

# 查看其他重要配置
mysql -u root -p -e "SHOW VARIABLES WHERE Variable_name IN ('sort_buffer_size', 'read_rnd_buffer_size', 'join_buffer_size');"
```

### 检查3：索引是否正确创建
```bash
# 查看EMRs表的所有索引
mysql -u root -p -e "SHOW INDEX FROM emrs;"

# 特别检查是否有 idx_emrs_patient_created_id 索引
mysql -u root -p -e "SHOW INDEX FROM emrs WHERE Key_name = 'idx_emrs_patient_created_id';"

# 分析查询执行计划
mysql -u root -p << 'EOF'
EXPLAIN SELECT emr_id, created_at FROM emrs 
WHERE patient_id = 'PA0793AA8CF11' AND archived = 0
ORDER BY created_at DESC LIMIT 100 \G
EOF

# 预期看到：
# type: range 或 index
# rows: <1000
# Extra: Using index 或 Using where, Using index
```

### 检查4：查询性能分析
```bash
# 启用慢查询日志（可选）
mysql -u root -p -e "SET GLOBAL slow_query_log = 1; SET GLOBAL long_query_time = 1;"

# 查看慢查询日志
tail -50 /var/log/mysql/slow-query.log

# 不禁忌使用索引的查询日志
mysql -u root -p -e "SET GLOBAL log_queries_not_using_indexes = 1;"
```

---

## ⚠️ 常见问题与解决

### Q1：执行sql脚本时提示权限不足
```
ERROR 1227 (42000): Access denied for user 'user'@'localhost'
```

**解决**：
```bash
# 使用root账户执行
sudo mysql -u root -p < mysql_optimization.sql

# 或者指定正确的MySQL用户
mysql -h 127.0.0.1 -u admin -p < mysql_optimization.sql
```

### Q2：应用重启后仍然超时
```bash
# 检查应用是否正确加载新代码
curl -s "http://localhost:8000/emr?patient_id=PA0793AA8CF11" 2>&1 | head

# 如果出现 503 错误仍然是 MySQL error 1038
# 说明MySQL配置未生效
# 需要重启MySQL：
sudo systemctl restart mysql
```

### Q3：索引创建提示"duplicate key"
```
ERROR 1061: Duplicate key name 'idx_emrs_patient_created_id'
```

**解决**：
```bash
# 索引已存在，不用重新创建
# 或手动删除后重建
mysql -u root -p -e "ALTER TABLE emrs DROP INDEX idx_emrs_patient_created_id;"
mysql -u root -p -e "ALTER TABLE emrs ADD INDEX idx_emrs_patient_created_id (patient_id, archived, created_at DESC, emr_id);"
```

### Q4：重启MySQL后应用连接超时
```
ERROR: MySQL connection refused
```

**解决**：
```bash
# 等待MySQL完全启动
sleep 5

# 检查MySQL状态
systemctl status mysql

# 检查MySQL监听端口
netstat -tulpn | grep 3306

# 强制重启应用
pkill -f uvicorn
sleep 2
cd /home/shuwen/emr/backend/device-ingestion
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

---

## 📋 完整执行清单

- [ ] **Step 1**：重启 FastAPI 应用
  - 命令：`sudo systemctl restart device-ingestion`
  - 验证：`curl http://localhost:8000/platform/summary` 返回 200

- [ ] **Step 2**：执行 MySQL 优化脚本
  - 命令：`mysql -u root -p < mysql_optimization.sql`
  - 耗时：< 1 分钟

- [ ] **Step 3**：验证 MySQL 配置
  - 命令：`mysql -u root -p -e "SHOW VARIABLES LIKE 'sort_buffer_size';"`
  - 预期：134217728 (128M)

- [ ] **Step 4**：验证索引创建
  - 命令：`mysql -u root -p -e "SHOW INDEX FROM emrs \G"`
  - 预期：看到 idx_emrs_patient_created_id

- [ ] **Step 5**：测试API端点
  - 命令：`curl "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true"`
  - 预期：200 OK，耗时 <1s

- [ ] **Step 6**：前端刷新验证
  - 打开浏览器
  - 刷新患者页面
  - 预期：快速加载，诊断报告显示

---

## 📝 性能基准测试

执行以下命令多次测试，收集性能数据：

```bash
# 批量测试（运行10次）
for i in {1..10}; do
  echo "=== Test $i ==="
  curl -s -w "HTTP %{http_code}, Time: %{time_total}s\n" \
    "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true" \
    -o /dev/null
  sleep 1
done

# 预期结果：所有请求都是 HTTP 200，时间 < 0.5s
```

---

## 🎯 下一步行动

### 立即（今天）
1. ✅ 重启应用：`sudo systemctl restart device-ingestion`
2. ✅ 执行SQL脚本：`mysql -u root -p < mysql_optimization.sql`
3. ✅ 验证修复：测试API和前端

### 短期（1-3天）
- [ ] 监控MySQL错误日志
- [ ] 收集性能指标
- [ ] 如有问题按诊断命令排查

### 中期（1-2周）
- [ ] 评估是否需要分页优化
- [ ] 考虑缓存策略
- [ ] 优化其他慢查询

---

## 📞 技术参考

| 文件 | 用途 |
|------|------|
| [QUICK_FIX.md](./QUICK_FIX.md) | ⏱️ 快速指南 |
| [PROBLEM_ANALYSIS.md](./PROBLEM_ANALYSIS.md) | 📖 问题分析 |
| [MYSQL_OPTIMIZATION.md](./MYSQL_OPTIMIZATION.md) | 🔧 参数详解 |
| [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) | ✓ 检查清单 |
| [mysql_optimization.sql](./mysql_optimization.sql) | 🔨 SQL脚本 |

---

## 最终确认

执行完成后，运行最终验证：

```bash
# 所有诊断命令在一起
echo "=== 1. 应用检查 ==="
ps aux | grep uvicorn | grep -v grep && echo "✅ 应用运行中" || echo "❌ 应用未运行"

echo ""
echo "=== 2. MySQL检查 ==="
mysql -u root -p -e "SELECT @@version, @@sort_buffer_size, @@max_connections;" 2>/dev/null

echo ""
echo "=== 3. API测试 ==="
curl -s -w "Status: %{http_code}, Time: %{time_total}s\n" \
  "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true" \
  -o /dev/null

echo ""
echo "✅ 部署完成！"
```

**预期输出**：
```
=== 1. 应用检查 ===
✅ 应用运行中

=== 2. MySQL检查 ===
版本: 5.7.x 或 8.0.x
sort_buffer_size: 134217728
max_connections: 151

=== 3. API测试 ===
Status: 200, Time: 0.35s

✅ 部署完成！
```

---

**状态**：🟢 **准备就绪** - 等待执行部署步骤

👉 **现在就开始**：
```bash
# 1. 重启应用
sudo systemctl restart device-ingestion

# 2. 执行SQL脚本  
mysql -u root -p < mysql_optimization.sql

# 3. 验证
curl "http://localhost:8000/emr?patient_id=PA0793AA8CF11&include_archived=true" -w "\n状态: %{http_code}, 耗时: %{time_total}s\n"
```
