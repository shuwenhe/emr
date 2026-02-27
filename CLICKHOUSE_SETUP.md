# ClickHouse 表初始化说明

## 快速开始

### 方式一：使用 Docker Compose（推荐）

1. **启动所有服务**：
```bash
docker-compose up -d
```

这会自动：
- 启动 MySQL 容器并创建 hospital 数据库和相关表
- 启动 ClickHouse 容器并创建 thermal 数据库和 thermal_timeseries 表
- 启动后端和前端服务

### 方式二：手动初始化（已有ClickHouse运行）

如果ClickHouse已经在运行（端口8124），运行：

```bash
python3 init_clickhouse.py
```

### 方式三：使用clickhouse-client命令行工具

连接到ClickHouse并执行初始化脚本：

```bash
clickhouse-client -h 127.0.0.1 -u hospital -p hospital < database/init_thermal.sql
```

## 表结构说明

### thermal.thermal_timeseries 表

存储热成像时间序列数据，主要字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| record_id | String | 采集记录ID（主键之一） |
| device_id | String | 设备ID |
| patient_id | String | 患者ID |
| capture_time | DateTime | 采集时间（分区键） |
| frame_id | String | 帧ID（主键之一） |
| row | UInt16 | 像素行坐标（主键之一） |
| col | UInt16 | 像素列坐标（主键之一） |
| temperature_c | Float32 | 温度值（摄氏度） |
| ingest_time | DateTime | 数据入库时间（默认为当前时间） |

**引擎**：MergeTree
**分区**：按月份分区 (PARTITION BY toYYYYMM(capture_time))
**排序键**：(record_id, frame_id, row, col)

## 数据同步

将MySQL中的采集数据同步到ClickHouse：

```bash
python3 sync_to_clickhouse.py
```

这个脚本会：
1. 连接到MySQL读取记录
2. 读取每条记录对应的CSV数据文件
3. 解析热成像像素数据
4. 批量插入到ClickHouse

## 验证表是否存在

### 通过HTTP接口
```bash
curl -s "http://127.0.0.1:8124/?user=hospital&password=hospital&database=thermal" \
  --data-binary "DESCRIBE TABLE thermal_timeseries"
```

### 通过 clickhouse-client
```bash
clickhouse-client -h 127.0.0.1 -u hospital -p hospital -d thermal \
  --query "DESCRIBE TABLE thermal_timeseries"
```

### 通过Python脚本
```python
from clickhouse_driver import Client

client = Client('127.0.0.1', port=9001, user='hospital', password='hospital')
result = client.execute('DESCRIBE TABLE thermal.thermal_timeseries')
for row in result:
    print(row)
```

## 配置文件

### config/clickhouse.yaml
ClickHouse连接配置：
```yaml
clickhouse:
  host: "localhost"
  port: 9001           # 原生协议端口
  database: "thermal"
  user: "hospital"
  password: "hospital"
```

### docker-compose.yml
ClickHouse服务配置：
```yaml
clickhouse:
  image: clickhouse/clickhouse-server:latest
  ports:
    - "9001:9000"      # 原生协议端口 (端口映射)
    - "8124:8123"      # HTTP接口端口 (端口映射)
  volumes:
    - ./database/init_clickhouse.sh:/docker-entrypoint-initdb.d/init_clickhouse.sh
```

## 常见问题

### Q: 无法连接到ClickHouse
A: 检查：
- ClickHouse 是否正在运行
- 端口 9001（原生协议）或 8124（HTTP）是否开放
- 用户名和密码是否正确（默认: hospital/hospital）

### Q: 表不存在
A: 
1. 检查初始化脚本是否运行成功
2. 查看 ClickHouse 日志：`docker logs hospital-clickhouse`
3. 手动运行 `python3 init_clickhouse.py`

### Q: 数据无法插入
A:
- 确保表已创建：`SHOW TABLES IN thermal`
- 检查表结构：`DESCRIBE TABLE thermal_timeseries`
- 检查插入SQL的数据类型是否匹配

## 测试表

插入测试数据：

```bash
clickhouse-client -h 127.0.0.1 -u hospital -p hospital -d thermal \
  --query "INSERT INTO thermal_timeseries VALUES \
    ('rec001', 'dev001', 'pat001', '2026-02-27 10:00:00', 'frame_0001', 0, 0, 36.5)"
```

查询数据：

```bash
clickhouse-client -h 127.0.0.1 -u hospital -p hospital -d thermal \
  --query "SELECT * FROM thermal_timeseries LIMIT 5"
```

## 性能优化

- 表按月份分区，便于时间范围查询
- 主键按 (record_id, frame_id, row, col) 排序，支持快速查找特定像素
- 适合大规模时间序列数据存储（数十亿行级别）

