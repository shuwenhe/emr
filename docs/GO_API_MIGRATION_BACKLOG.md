# Go API 迁移 Backlog（逐接口可执行）

> 目标：在不破坏现网行为的前提下，将适合的 API 逐步迁移到 Go，实现“Go 网关 + Python AI 核心”混合架构。

## 迁移原则

1. **先迁 I/O 接口，后迁业务接口**。
2. **每批仅迁一组接口**，必须有回滚开关。
3. **响应 JSON 字段保持兼容**（字段名、空值、状态码）。
4. Python 保留 `ingest/analyze/AI/RAG` 核心逻辑。

---

## 批次 A（P0）先迁 Go：Reports 全量

### 接口清单
- `GET /reports`
- `GET /reports/{date}/{filename}`
- `GET /reports/preview`
- `GET /reports/.trash`
- `GET /reports/.trash/{date}/{filename}`
- `POST /reports/archive`

### 当前状态
- Python 已支持 Go 代理转发（`ENABLE_GO_REPORT_PROXY`）。
- 文件：`api/routes/reports.py`。

### 迁移动作
1. Go 服务实现并对齐上述 6 个接口返回结构。
2. Python 保留转发层作为兼容壳（短期）。
3. 通过开关切流：灰度环境先 `ENABLE_GO_REPORT_PROXY=true`。

### 验收标准
- 与 Python 旧实现响应字段一致：`date/name/size_bytes/url/updated_at`。
- 下载与预览 `Content-Disposition` 兼容。
- 归档/恢复行为一致（含 404/409）。

### 回滚
- 一键切回：`ENABLE_GO_REPORT_PROXY=false`。

---

## 批次 B（P0/P1）迁 Go：Platform 查询接口

### 接口清单
- `GET /platform/summary`
- `GET /platform/records`
- `GET /platform/emrs`

### 迁移动作
1. 在 Go 实现只读查询接口。
2. Python 路由层增加可选代理（同 reports 模式）。
3. 先灰度 summary，再 records/emrs。

### 验收标准
- 分页、排序、归档过滤语义一致。
- 响应耗时不劣化（P95 持平或更优）。

### 回滚
- 切回 Python `PlatformService` 直查路径。

---

## 批次 C（P1）迁 Go：Patients CRUD

### 接口清单
- `POST /patients`
- `GET /patients`
- `GET /patients/{patient_id}`
- `PUT /patients/{patient_id}`
- `POST /patients/{patient_id}/archive`
- `DELETE /patients/{patient_id}`
- `POST /patients/batch-delete`

### 迁移动作
1. 先迁只读（GET），再迁写（POST/PUT/DELETE）。
2. 对齐错误码：`400/404` 与 `detail` 文本。
3. 保持 `patient_id` 自动生成规则兼容。

### 验收标准
- 患者增删改查行为与当前前端兼容。
- 批量删除返回结构一致。

### 回滚
- 路由切回 Python `PlatformService`。

---

## 批次 D（P1）迁 Go：EMR 查询接口（只读优先）

### 接口清单
- `GET /emr`
- `GET /emr/{emr_id}`

### 暂不迁（保留 Python）
- `POST /emr/generate`
- `PUT /emr/{emr_id}`

### 原因
- 生成与更新链路涉及 docx 回填、AI 字段回写，Python 逻辑已稳定。

---

## 长期保留 Python（P2 之后再评估）

### 接口清单
- `POST /ingest`
- `POST /device/ingest`
- `POST /analyze`
- `POST /dispatch`

### 原因
- 强依赖 Python 分析、LLM、RAG 生态；迁移成本最高。

---

## 每批次通用验证清单

1. **契约一致性**：状态码、字段、空值行为。
2. **回归接口**：
   - `/patients`
   - `/emr`
   - `/reports`
   - `/platform/*`
3. **日志链路**：request_id / record_id 可追踪。
4. **回滚演练**：开关切回后 5 分钟内恢复。

---

## 立即执行建议（本周）

1. 先做批次 A（Reports）并完成契约对齐。
2. 然后做批次 B（Platform 查询）中的 `/platform/summary`。
3. 每完成一项接口迁移，在此文档勾选状态并记录发布日期。
