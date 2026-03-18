# 设备接入服务（Device Ingestion）

该服务用于接入红外设备数据，完成基础校验（QC）与落盘存储。

数据平台索引使用 MySQL（配置见 app/config.py，默认数据库/用户/密码均为 hospital）。

## 启动方式
1. 使用 Python 3.12（推荐）
2. 安装依赖
3. 启动服务（本地开发）

## 生产部署（开机自启 + 异常自动重启）
如果你是通过 `uvicorn ... &` 手工启动，服务器重启后进程不会自动恢复。

项目已提供 `systemd` 安装脚本：

1. 安装并启用服务

  ```bash
  cd /home/shuwen/emr
  ./scripts/deployment/install_systemd_service.sh
  ```

2. 查看状态

  ```bash
  sudo systemctl status emr-ingestion
  ```

3. 追踪日志

  ```bash
  sudo journalctl -u emr-ingestion -f
  tail -f /home/shuwen/emr/logs/emr-ingestion.out.log
  tail -f /home/shuwen/emr/logs/emr-ingestion.err.log
  ```

默认使用：
- 工作目录：`/home/shuwen/emr`
- 入口模块：`route.main:app`
- 端口：`8000`

可通过环境变量自定义安装（示例）：

```bash
SERVICE_NAME=emr-api APP_PORT=8010 APP_MODULE=route.main:app ./scripts/deployment/install_systemd_service.sh
```

## Nginx 反向代理与健康检查
为避免外网访问偶发不可达，建议在后端前增加 Nginx 反向代理并启用健康探针。

1. 安装并加载 Nginx 配置

  ```bash
  cd /home/shuwen/emr
  ./scripts/deployment/install_nginx_proxy.sh
  ```

2. 验证探针

  ```bash
  curl -i http://127.0.0.1/nginx-healthz
  curl -i http://127.0.0.1/healthz
  curl -i http://127.0.0.1/readyz
  ```

默认上游：
- 后端：`127.0.0.1:8000`
- 前端：`127.0.0.1:3000`

可按需覆盖：

```bash
SERVER_NAME=example.com BACKEND_UPSTREAM=127.0.0.1:8000 FRONTEND_UPSTREAM=127.0.0.1:3000 ./scripts/deployment/install_nginx_proxy.sh
```

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
