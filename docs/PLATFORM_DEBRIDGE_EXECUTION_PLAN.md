# Platform Service 去 Legacy 桥接执行清单

## 目标
在不影响现有 API 行为的前提下，逐步移除 `services/platform/__init__.py` 中对 `ingestion/app/*` 的 `sys.path + importlib` 动态桥接，建立可测试、可维护的本地实现。

当前桥接点见：
- `services/platform/__init__.py`
- `api/routes/platform.py`
- `api/routes/patients.py`
- `api/routes/emr.py`（调用 `list_platform_emrs`）

---

## 现状问题（精确）
1. `PlatformService` 动态加载 legacy 模块（`app.data_platform` / `app.device_connector` / `app.analysis`），运行时隐式依赖强。
2. 业务边界不清：平台服务直接穿透到 legacy 数据访问细节。
3. 单元测试难做：方法依赖运行时导入和外部文件结构。
4. 错误语义不统一：legacy 异常直接冒泡，API 层约束弱。

---

## 迁移策略（分阶段、可回滚）
采用 **Strangler Fig**（绞杀者）策略：
- 每次只替换一组方法，保留旧行为兜底。
- 每完成一组方法就补测试并验证 API。
- 若异常，切回 legacy 适配层。

---

## 阶段 0：建立适配层边界（1 天）

### 改动文件
- `services/platform/__init__.py`
- 新增：`services/platform/legacy_adapter.py`
- 新增：`services/platform/types.py`

### 动作
1. 把现有 importlib 逻辑迁到 `legacy_adapter.py`，`PlatformService` 只依赖适配器接口。
2. 在 `types.py` 定义最小返回协议（患者、记录、EMR、汇总）。
3. `PlatformService` 保持外部方法签名不变（避免路由变更）。

### 验收
- `api/routes/platform.py`、`api/routes/patients.py` 无需改动即可运行。
- 接口响应字段与当前一致。

### 回滚
- 直接恢复 `services/platform/__init__.py` 到当前版本。

---

## 阶段 1：先替换“纯查询”能力（2 天）

### 优先替换方法
- `summary()`
- `list_records()`
- `list_platform_emrs()`
- `list_patients()`
- `get_patient()`

### 新增文件
- `repositories/patient_repository.py`
- `repositories/record_repository.py`
- `repositories/emr_repository.py`
- `repositories/summary_repository.py`

### 动作
1. 在 repositories 中实现只读查询（先对齐现有 SQL 语义，不做功能增强）。
2. `PlatformService` 内按 feature flag 切换：
   - 默认新实现；
   - 异常时可降级 legacy。
3. 增加字段归一化层，确保日期/布尔/空值格式与当前前端兼容。

### 验收
- `/platform/summary`、`/platform/records`、`/platform/emrs`、`/patients`、`/patients/{id}` 响应结构不变。
- 基准数据下查询耗时不劣于当前 10%。

### 回滚
- flag 切回 legacy 查询。

---

## 阶段 2：替换“写操作”能力（2 天）

### 替换方法
- `upsert_patient()`
- `update_patient()`
- `archive_patient()`
- `delete_patient()`

### 动作
1. 将写操作下沉到 `patient_repository.py`，统一事务处理。
2. 显式返回成功/失败原因（not found / conflict / validation）。
3. 在 API 层保持原状态码和 detail 字段不变。

### 验收
- `/patients` POST/PUT/DELETE/ARCHIVE 行为与当前一致。
- 并发下无脏写（至少覆盖基础并发测试）。

### 回滚
- 对写路径保留 legacy adapter fallback。

---

## 阶段 3：设备轮询与历史导入解耦（2-3 天）

### 替换方法
- `poll_device_drop()`
- `import_history()`
- `init_db()`

### 动作
1. 新建 `services/device_ingestion_service.py`，把设备目录扫描、导入、分析串联迁出 `PlatformService`。
2. `PlatformService` 仅保留“平台查询/患者管理”职责。
3. `api/main.py` 启动任务改为注入 `DeviceIngestionService`。

### 验收
- 启动时轮询行为与当前一致。
- `/import/history` 返回字段保持兼容（`ingested/skipped/analyzed`）。

### 回滚
- `api/main.py` 切回当前 `platform_service.poll_device_drop` 调用。

---

## 阶段 4：移除桥接与清理（1 天）

### 动作
1. 删除 `sys.path` 注入与 `importlib` legacy 依赖。
2. 将 `legacy_adapter.py` 标记废弃后移除。
3. 文档同步：
   - `docs/ARCHITECTURE.md`
   - `docs/API_SPECIFICATION.md`
   - `docs/PROJECT_METHODOLOGY.md`

### 验收
- `services/platform/__init__.py` 不再引用 `ingestion/app/*`。
- CI 全量通过。

---

## 测试清单（每阶段执行）

### API 回归
- `GET /platform/summary`
- `GET /platform/records?limit=50`
- `GET /platform/emrs?limit=50`
- `GET /patients?page=1&limit=20`
- `POST /patients` + `PUT /patients/{id}` + `POST /patients/{id}/archive` + `DELETE /patients/{id}`
- `POST /import/history`

### 数据一致性
- 同一患者在迁移前后查询结果字段一致。
- EMR 列表排序、分页、归档过滤一致。

### 性能基线
- `/patients` P95
- `/platform/emrs` P95
- `/platform/summary` P95

---

## 风险与控制
1. **SQL 语义漂移**：先复用现有查询逻辑，再重构结构。
2. **字段兼容性**：增加 response contract test（JSON schema）。
3. **轮询任务副作用**：设备导入拆分阶段单独灰度。
4. **发布风险**：保留 feature flag 与 legacy fallback 至阶段 4 完成。

---

## 建议的首批 PR 切分
1. PR-1：`legacy_adapter.py + PlatformService 适配层`（无行为变化）
2. PR-2：查询方法迁移 + 查询回归测试
3. PR-3：患者写操作迁移 + 事务与错误映射测试
4. PR-4：设备导入职责拆分到 `DeviceIngestionService`
5. PR-5：移除 legacy bridge + 文档收尾

---

## 完成定义（DoD）
- `services/platform` 无动态导入 legacy 代码。
- 平台/患者 API 行为不变且测试通过。
- 启动路径和轮询任务清晰分层。
- 文档与目录结构一致，无旧路径残留。
