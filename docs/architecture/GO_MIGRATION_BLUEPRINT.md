# EMR Go 落地蓝图（混合架构）

## 1. 目标与原则

### 目标
- 在不影响现有 Python 业务能力（AI/RAG/分析）的前提下，引入 Go 提升：
  - 高并发 I/O 吞吐
  - 长期稳定性（低内存、低延迟）
  - 任务调度与可观测性

### 原则
- **先边缘，后核心**：先迁移 I/O 密集服务，不直接改动诊断算法与 RAG 主链路。
- **接口先行**：先定义 HTTP/gRPC 契约，再迁移实现。
- **可回滚**：每个阶段保留 Python fallback 路由。
- **分层解耦**：Go 负责网关/文件/任务调度，Python 保持领域计算与AI能力。

---

## 2. 建议的 Go 服务边界

## 2.1 `go-report-file-service`（优先级 P0）

### 迁移来源
- 当前 `src/backend/api/routes/reports.py` 中的：
  - 报告列表
  - 报告下载/预览
  - 报告归档/恢复
  - 缓存逻辑

### 适配原因
- 纯 I/O + 文件系统操作，Go 在并发下载、目录遍历、缓存控制上更稳定。
- 业务耦合低，风险最小，收益快。

### 对外职责
- 管理 `reports/` 和 `.trash` 目录
- 提供查询、下载、归档接口
- 提供缓存失效与基础审计日志

---

## 2.2 `go-ingestion-gateway`（优先级 P1）

### 迁移来源
- 当前 `src/backend/api/routes/ingest.py` 的接入入口
- 当前 `src/backend/services/platform/__init__.py` 的轮询触发入口

### 适配原因
- 上传、目录监听、并发消费属于高并发 I/O 场景。
- Go 更容易做 backpressure、限流、超时控制、连接复用。

### 对外职责
- 文件上传入口（鉴权、限速、大小校验）
- 投递分析任务到 Python（HTTP/gRPC/队列）
- 设备目录轮询调度与重试

---

## 2.3 `go-batch-worker`（优先级 P1）

### 迁移来源
- `scripts/`、`ingestion/` 下批处理脚本（如同步、补数、批量生成）

### 适配原因
- 任务编排、重试、并发 worker 池、死信管理，Go 实现更轻量且稳定。

### 对外职责
- 定时任务（cron）
- 批任务并发执行
- 失败重试 + 幂等控制
- 任务状态查询

---

## 2.4 `go-api-gateway`（优先级 P2）

### 迁移来源
- 当前 FastAPI 入口层的通用能力（未来）

### 对外职责
- 统一鉴权（JWT/OIDC）
- 限流、熔断、超时
- 路由到 Python/Go 子服务
- 请求追踪与统一日志字段注入

---

## 3. 不建议迁移到 Go 的模块（当前阶段）

- `rag/`（embedding、kb 处理）
- 热成像分析主逻辑（NumPy/算法/模型）
- AI 报告与诊断推理链路
- ROI C++ 计算核心

建议保持：**Python + C++** 作为“计算内核”，Go 作为“系统外壳与调度层”。

---

## 4. 接口契约建议（首批）

## 4.1 Report File Service API

### `GET /v1/reports?date=YYYY-MM-DD`
- 返回：
```json
[
  {
    "date": "2026-03-11",
    "name": "张三_20260311_101530.docx",
    "size_bytes": 123456,
    "url": "/v1/reports/2026-03-11/张三_20260311_101530.docx",
    "updated_at": 1741678530
  }
]
```

### `GET /v1/reports/{date}/{filename}?inline=true|false`
- 返回文件流（支持 `Content-Disposition` 与 UTF-8 文件名）

### `POST /v1/reports/archive`
- 请求：
```json
{ "date": "2026-03-11", "filename": "a.docx", "archived": true }
```
- 响应：
```json
{ "status": "archived", "date": "2026-03-11", "filename": "a.docx" }
```

### `GET /v1/reports/trash`
- 列出归档区文件

---

## 4.2 Ingestion Gateway API（对前端）

### `POST /v1/ingest`
- multipart 上传 + metadata
- 网关负责：
  - 文件后缀/大小校验
  - 反压（队列满返回 429）
  - 投递 Python 分析服务

### `POST /v1/device/scan`
- 触发目录扫描任务

### `GET /v1/tasks/{id}`
- 查询处理状态（pending/running/success/failed）

---

## 5. 建议的目录结构（新增）

```text
emr/
├── go-services/
│   ├── report-file-service/
│   │   ├── cmd/server/main.go
│   │   ├── internal/handler/
│   │   ├── internal/service/
│   │   ├── internal/repository/
│   │   ├── internal/config/
│   │   ├── internal/cache/
│   │   ├── go.mod
│   │   └── Dockerfile
│   │
│   ├── ingestion-gateway/
│   │   ├── cmd/server/main.go
│   │   ├── internal/handler/
│   │   ├── internal/queue/
│   │   ├── internal/client/python/
│   │   ├── internal/config/
│   │   ├── go.mod
│   │   └── Dockerfile
│   │
│   └── batch-worker/
│       ├── cmd/worker/main.go
│       ├── internal/jobs/
│       ├── internal/scheduler/
│       ├── internal/store/
│       ├── go.mod
│       └── Dockerfile
├── docker/
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
└── docs/architecture/GO_MIGRATION_BLUEPRINT.md
```

---

## 6. 两周迁移计划（可执行）

## Week 1（先拿低风险收益）

### Day 1-2
- 建立 `go-services/report-file-service` 基础工程
- 对齐 `reports.py` 接口契约
- 打通本地 `reports/`、`.trash` 目录读取

### Day 3-4
- 完成列表/下载/归档接口
- 加入内存缓存 TTL（与当前行为一致）
- 增加基础单测 + 压测脚本

### Day 5
- 在 `docker-compose` 增加 `report-file-service`
- FastAPI 保留原路由，新增开关（env）切换至 Go 服务（灰度）

## Week 2（扩展并发入口）

### Day 6-7
- 建立 `ingestion-gateway` 上传入口
- 实现限流、文件大小与类型校验

### Day 8-9
- 实现任务投递到 Python 分析服务
- 增加任务状态查询与失败重试

### Day 10
- 压测与稳定性回归
- 产出切换预案与回滚预案

---

## 7. 关键非功能需求（NFR）

- **可用性**：接口超时控制（如 3s/10s 分层）
- **稳定性**：幂等键 + 重试上限 + 死信策略
- **安全性**：输入校验、路径穿越防护、统一鉴权
- **可观测性**：
  - 结构化日志（trace_id、patient_id、record_id）
  - Prometheus 指标（QPS、P95、错误率、队列深度）
  - OpenTelemetry trace

---

## 8. 风险与回滚

### 风险
- 与现有 Python 路由语义不一致（header、错误码、文件名编码）
- 文件系统并发写冲突
- 灰度期间双写/双读不一致

### 回滚策略
- 保留 FastAPI 原接口实现
- 通过 env 开关快速切回 Python
- 关键接口保留 contract test，确保协议一致

---

## 9. 第一阶段验收标准（Definition of Done）

- `report-file-service` 覆盖原 `reports.py` 的核心能力
- 压测下 P95 延迟优于当前基线或持平但更稳定
- 错误码与响应结构与现网契约一致
- 灰度可切换、回滚可在分钟级完成

---

## 10. 下一步建议

- 先从 `reports.py` 提炼 OpenAPI 契约并锁定（避免迁移过程中协议漂移）
- 我可以继续给你输出：
  1. `report-file-service` 的最小可运行 Go 骨架代码
  2. 与 FastAPI 对齐的 contract test 样例
  3. `docker-compose` 增量改造清单
