# Hospital 项目数据库初始化完成

## ✅ 已完成的配置

### MySQL 数据库（hospital）
- **主机**: 127.0.0.1:3306
- **用户**: hospital
- **密码**: hospital
- **数据库**: hospital

已创建的表：
1. **patients** - 患者信息表
2. **records** - 采集记录表
3. **reports** - 分析报告表
4. **plans** - 治疗计划表
5. **emrs** - 电子病历表

### ClickHouse 数据库（hospital）
- **主机**: 127.0.0.1
- **原生协议端口**: 9000
- **HTTP接口端口**: 8123
- **用户**: hospital
- **密码**: hospital
- **数据库**: hospital

已创建的表：
1. **thermal_timeseries** - 热成像时间序列数据表
   - 主键: (record_id, frame_id, row, col)
   - 分区: 按月份分区 (toYYYYMM(capture_time))
   - 字段: record_id, device_id, patient_id, capture_time, frame_id, row, col, temperature_c, ingest_time

## 📝 相关文件

### 初始化脚本
- `/home/shuwen/hospital-report/database/init_mysql.sql` - MySQL初始化脚本
- `/home/shuwen/hospital-report/database/init_clickhouse.sh` - ClickHouse初始化脚本
- `/home/shuwen/hospital-report/database/init_thermal.sql` - ClickHouse SQL脚本
- `/home/shuwen/hospital-report/init_clickhouse.py` - Python初始化脚本

### 配置文件
- `/home/shuwen/hospital-report/config/mysql.yaml` - MySQL连接配置
- `/home/shuwen/hospital-report/config/clickhouse.yaml` - ClickHouse连接配置
- `/home/shuwen/hospital-report/docker-compose.yml` - Docker Compose配置

### 数据同步
- `/home/shuwen/hospital-report/sync_to_clickhouse.py` - MySQL到ClickHouse数据同步脚本

## 🚀 快速开始

### 使用Docker启动所有服务
```bash
cd /home/shuwen/hospital-report
docker-compose up -d
```

这会自动：
- 创建并启动MySQL容器（hospital数据库）
- 创建并启动ClickHouse容器（hospital数据库+thermal_timeseries表）
- 启动后端API服务
- 启动前端应用

### 验证数据库连接

#### MySQL
```bash
mysql -h 127.0.0.1 -u hospital -p hospital hospital
> SHOW TABLES;
> DESCRIBE patients;
```

#### ClickHouse
```bash
# 通过HTTP接口
curl -u hospital:hospital "http://127.0.0.1:8123/" --data-binary "SHOW TABLES IN hospital"

# 通过原生协议
clickhouse-client -h 127.0.0.1 -u hospital -p hospital -d hospital --query "SHOW TABLES"
```

## 📊 数据流

1. **数据采集** → 上传至 `/device-drop` 目录
2. **数据处理** → 后端API处理，保存到MySQL
3. **时序数据** → 热成像像素数据同步到ClickHouse
4. **数据分析** → 从ClickHouse查询时序数据进行分析
5. **报告生成** → 生成DOCX格式的分析报告

## 🔧 常用命令

### 初始化ClickHouse（如果容器未自动初始化）
```bash
python3 /home/shuwen/hospital-report/init_clickhouse.py
```

### 同步MySQL数据到ClickHouse
```bash
python3 /home/shuwen/hospital-report/sync_to_clickhouse.py
```

### 查询ClickHouse数据
```bash
clickhouse-client -h 127.0.0.1 -u hospital -p hospital -d hospital \
  --query "SELECT COUNT(*) FROM thermal_timeseries"
```

### 查询MySQL数据
```bash
mysql -h 127.0.0.1 -u hospital -p hospital hospital \
  -e "SELECT COUNT(*) FROM records"
```

## ⚠️ 常见问题

### Q: ClickHouse表不存在
A: 运行 `python3 init_clickhouse.py` 手动初始化

### Q: 无法连接到ClickHouse
A: 检查：
- ClickHouse 容器是否运行: `docker ps | grep clickhouse`
- 端口映射是否正确: `docker port hospital-clickhouse`
- 防火墙设置

### Q: MySQL表不存在
A: 查看初始化日志：`docker logs hospital-mysql`

## 📚 更多信息

详见: `/home/shuwen/hospital-report/CLICKHOUSE_SETUP.md`
