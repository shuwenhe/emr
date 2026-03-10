# 设备接入服务（Device Ingestion）

该服务用于接入红外设备数据，完成基础校验（QC）与落盘存储。

数据平台索引使用 MySQL（配置见 app/config.py，默认数据库/用户/密码均为 hospital）。

## 启动方式
1. 使用 Python 3.12（推荐）
2. 安装依赖
3. 启动服务（本地开发）

## API
- POST /ingest
  - 表单字段：
    - file: 红外数据文件（如二进制或序列化文件）
    - metadata: JSON 字符串，包含采集参数与环境信息

- POST /device/ingest
  - JSON Body：
    - capture_path: 设备落盘目录（可选，缺省扫描 device-drop）
    - move_to_processed: 入库后是否移动到 device-processed（默认 true）

- POST /import/history
  - JSON Body：
    - root_path: 历史数据根目录（子目录含 metadata.json 与数据文件）
    - analyze: 是否自动生成报告/病历（默认 true）

- POST /emr/generate
  - JSON Body：
    - record_id: 采集记录 ID

- GET /emr/{emr_id}
- GET /emr?patient_id=<patient_id>
- PUT /emr/{emr_id}
- POST /emr/{emr_id}/archive

- GET /platform/summary
- GET /platform/records?patient_id=<patient_id>&limit=50
- GET /platform/emrs?patient_id=<patient_id>&limit=50

## 设备直连（本地落盘模拟）
- 设备将一次采集写入 device-drop/子目录
- 子目录至少包含：metadata.json 与一个数据文件（.csv/.bin/.dat/.npy/.zip）
- 服务启动后自动扫描并入库（5秒轮询）

返回：
- record_id: 存储记录 ID
- storage_path: 文件落盘路径

> 说明：详细字段见 ../../docs/设备接入接口.md
