# 7天优化执行清单（可直接开工）

> 目标：先解决“架构双核心 + 大页面 + 数据目录混乱”，不做大爆破迁移。

## Day 1：平台层去桥接（建立适配边界）

### 要做什么
- 把 `services/platform` 对 `ingestion/app/*` 的动态桥接抽到独立适配器。
- `PlatformService` 本体只依赖接口，不直接 `importlib + sys.path`。

### 文件清单
- 修改：`services/platform/__init__.py`
- 新增：`services/platform/legacy_adapter.py`
- 新增：`services/platform/types.py`

### 验收标准
- `api/routes/platform.py`、`api/routes/patients.py` 无需改行为。
- 接口字段保持兼容。
- 仍可通过 legacy fallback 跑通。

---

## Day 2：迁查询路径（低风险高收益）

### 要做什么
- 先迁纯查询：`summary / list_records / list_platform_emrs / list_patients / get_patient`。
- repositories 只做“行为对齐”，暂不做增强。

### 文件清单
- 新增：`repositories/patient_repository.py`
- 新增：`repositories/record_repository.py`
- 新增：`repositories/emr_repository.py`
- 新增：`repositories/summary_repository.py`
- 修改：`services/platform/__init__.py`

### 验收标准
- `GET /platform/summary`
- `GET /platform/records`
- `GET /platform/emrs`
- `GET /patients`
- `GET /patients/{id}`

响应结构与当前前端兼容。

---

## Day 3：迁写操作（患者域）

### 要做什么
- 迁患者写路径：`upsert / update / archive / delete`。
- 统一错误映射（not found / validation / conflict）。

### 文件清单
- 修改：`services/platform/__init__.py`
- 修改：`repositories/patient_repository.py`
- 视情况补：`core/exceptions.py`
- 视情况补：`api/routes/patients.py`（仅错误语义对齐）

### 验收标准
- `POST /patients`
- `PUT /patients/{id}`
- `POST /patients/{id}/archive`
- `DELETE /patients/{id}`

状态码和 `detail` 语义稳定。

---

## Day 4：EMR页面拆分第一刀（不改交互）

### 要做什么
- 把 `emr/page.tsx` 拆成“容器 + 展示组件”。
- 先拆不涉及状态机的大块渲染。

### 文件清单
- 修改：`web/src/app/emr/page.tsx`
- 新增：`web/src/components/features/emr/EmrSummaryCard.tsx`
- 新增：`web/src/components/features/emr/EmrReportPanel.tsx`
- 新增：`web/src/components/features/emr/EmrHistoryTable.tsx`
- 新增：`web/src/components/features/emr/EmrEvidencePanel.tsx`

### 验收标准
- 页面功能不变（查询、保存、导出、历史报告、证据展示）。
- 逻辑回归通过（至少手工回归一轮）。

---

## Day 5：Patients页面拆分 + 历史报告逻辑收敛

### 要做什么
- 把患者页面的列表、详情、历史报告弹层拆分。
- 保留你已修复的“过滤 + fallback”行为。

### 文件清单
- 修改：`web/src/app/patients/page.tsx`
- 新增：`web/src/components/features/patients/PatientTable.tsx`
- 新增：`web/src/components/features/patients/PatientDetailModal.tsx`
- 新增：`web/src/components/features/patients/PatientReportHistoryModal.tsx`
- 新增：`web/src/hooks/usePatientReportHistory.ts`

### 验收标准
- 历史报告显示逻辑不回退。
- 日期过滤仍基于完整集合重算。

---

## Day 6：路径治理（统一 storage）

### 要做什么
- 统一运行时数据目录到 `storage/*`。
- 降低 `data/`、`logs/`、`storage/` 职责重叠。

### 文件清单
- 修改：`core/config.py`
- 修改：`api/routes/reports.py`
- 修改：`ingestion/app/emr.py`
- 修改：`ingestion/app/config.py`
- 修改：`.env.example`
- 修改：`docs/ARCHITECTURE.md`

### 验收标准
- 报告生成、历史列表、下载、预览路径一致。
- 日志目录行为明确（推荐 `storage/logs`）。

---

## Day 7：回归与守护（测试 + 文档）

### 要做什么
- 补关键回归测试，固化最近修复成果。
- 同步文档，避免“代码已改文档还旧”。

### 文件清单
- 新增/修改：`tests/` 下 API 回归（patients/emr/reports/ingest）
- 修改：`docs/ARCHITECTURE.md`
- 修改：`docs/REFACTOR_PLAN.md`
- 修改：`docs/PLATFORM_DEBRIDGE_EXECUTION_PLAN.md`（进度勾选）

### 验收标准
- 覆盖最近高风险链路：
  - docx 回填
  - reports 缓存失效
  - AI evidence 持久化与展示
- 文档与现状一致。

---

## 每天通用检查清单（建议固定执行）

- 后端：`python3 -m py_compile api/routes/ingest.py ingestion/app/emr.py ingestion/app/llm_report.py`
- 前端：`cd web && npm run lint`（允许已有历史问题，但不能引入新问题）
- 接口冒烟：`/patients`、`/emr`、`/reports`、`/ingest`
- 日志核对：`storage/logs/app.log` 是否有异常堆栈

---

## 边界原则（避免做过头）

1. 先迁职责，不先搬目录。
2. 每天最多一个高风险点（例如“写路径迁移”）。
3. 每个 PR 必须可回滚。
4. 前端拆分不改交互语义。
5. 文档跟着改动当天更新，不拖。
