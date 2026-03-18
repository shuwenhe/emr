# Gin 路由映射表（Python -> Go）

## 启动入口

- 现有服务入口（保留）：[reports/go/cmd/server/main.go](reports/go/cmd/server/main.go)
- Gin 骨架入口（新增）：[reports/go/cmd/ginserver/main.go](reports/go/cmd/ginserver/main.go)

---

## 已定义 Gin 路由（骨架）

| 分类 | Gin 路径 | 方法 | 对应 Python 路径 |
|---|---|---|---|
| Health | `/healthz` | GET | `/healthz`（Go服务健康） |
| Reports | `/v1/reports` | GET | `/reports` |
| Reports | `/v1/reports/trash` | GET | `/reports/.trash` |
| Reports | `/v1/reports/:date/:filename` | GET | `/reports/{date}/{filename}` |
| Reports | `/v1/reports/trash/:date/:filename` | GET | `/reports/.trash/{date}/{filename}` |
| Reports | `/v1/reports/archive` | POST | `/reports/archive` |
| Platform | `/v1/platform/summary` | GET | `/platform/summary` |
| Platform | `/v1/platform/records` | GET | `/platform/records` |
| Platform | `/v1/platform/emrs` | GET | `/platform/emrs` |

---

## Python 代理映射关系

### 已接入 Go 灰度代理
- `/reports/*`（带健康探测与 fail-open）：[api/routes/reports.py](api/routes/reports.py)
- `/platform/summary`（带健康探测与 fail-open）：[api/routes/platform.py](api/routes/platform.py)
- `/platform/records`（带健康探测与 fail-open）：[api/routes/platform.py](api/routes/platform.py)

### 下一步建议接入
- `/platform/emrs`

---

## 实现顺序建议（Gin）

1. `PlatformRecords`（优先）
2. `PlatformSummary`
3. `PlatformEMRs`
4. `ListReports` / `DownloadReport` / `ArchiveReport`
5. `ListTrashReports` / `DownloadTrashReport`

---

## 契约对齐要点

1. 保持 JSON 字段名一致（含 `detail` 错误字段）。
2. 文件下载必须保留 `Content-Disposition` 行为。
3. 分页/过滤参数命名与默认值一致（如 `limit`、`patient_id`）。
4. Go 不可用时由 Python fail-open 回退到本地实现。
