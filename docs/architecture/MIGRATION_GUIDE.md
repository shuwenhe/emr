# EMR 架构重构迁移指南

## 重构概述

本次重构将 EMR 系统从单体应用升级为符合工业标准的分层架构，主要改进包括：

✅ **服务分层** - 清晰的 API/Service/Repository 分层
✅ **统一配置** - 基于环境的配置管理（12-Factor App）
✅ **模块化** - 职责单一的服务模块
✅ **可测试性** - 依赖注入和接口抽象
✅ **可维护性** - 标准化的目录结构和命名

---

## 目录结构对比

### 旧结构 (Legacy)
```
emr/
├── backend/
│   └── device-ingestion/          # 单体应用
│       ├── app/                   # 所有业务逻辑混在一起
│       │   ├── analysis.py
│       │   ├── emr.py
│       │   ├── config.py
│       │   └── main.py
│       ├── batch_generate_reports.py  # 脚本散落
│       └── fix_emr_patient_ids.py
├── data/                          # 9.2GB 数据在根目录
├── reports/                       ❌ 混乱
├── config/                        # 配置分散
└── tests/                         # 测试不规范
```

### 新结构 (Refactored) ✅
```
emr/
├── src/                           # ⭐ 源代码主目录
│   └── backend/
│       ├── api/                   # API 网关层
│       ├── services/              # ⭐ 业务服务层（关键改进）
│       │   ├── ingestion/         # 数据接入服务
│       │   ├── analysis/          # 分析服务
│       │   ├── emr/               # EMR 管理服务
│       │   ├── reports/           # 报告生成服务 ✅
│       │   ├── treatment/         # 治疗方案服务
│       │   └── ai/                # AI 服务
│       ├── core/                  # ⭐ 核心基础设施
│       │   ├── config.py          # 统一配置 ✅
│       │   ├── exceptions.py      # 异常体系 ✅
│       │   └── logging.py         # 日志管理 ✅
│       ├── models/                # 数据模型
│       ├── repositories/          # 数据访问层
│       └── utils/                 # 工具函数
│
├── config/                        # ⭐ 环境配置（YAML）✅
│   ├── default.yaml
│   ├── development.yaml
│   ├── production.yaml
│   └── test.yaml
│
├── storage/                       # ⭐ 运行时数据（不提交Git）✅
│   ├── data/                      # 患者数据
│   ├── reports/                   # 生成的报告
│   ├── logs/                      # 应用日志
│   ├── cache/                     # 缓存
│   └── uploads/                   # 用户上传
│
├── scripts/                       # ⭐ 规范化的脚本 ✅
│   ├── db/                        # 数据库脚本
│   ├── data_processing/           # 数据处理工具
│   └── deployment/                # 部署脚本
│
├── tests/                         # ⭐ 规范化测试 ✅
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   └── e2e/                       # 端到端测试
│
├── requirements/                  # ⭐ 分环境依赖管理 ✅
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
│
├── .env.example                   # ⭐ 环境变量模板 ✅
└── README.md                      # ⭐ 更新的项目文档 ✅
```

---

## 迁移步骤

### Phase 1: 基础设施（已完成）✅

- [x] 创建新目录结构
- [x] 建立核心配置管理层 (`src/backend/core/`)
- [x] 创建环境配置文件 (`config/*.yaml`)
- [x] 创建依赖管理文件 (`requirements/`)
- [x] 更新 `.gitignore` 和 `.env.example`

### Phase 2: 服务骨架（已完成）✅

- [x] 创建 `ingestion` 服务骨架
- [x] 创建 `analysis` 服务骨架
- [x] 创建 `emr` 服务骨架
- [x] 创建 `treatment` 服务骨架
- [x] 创建 `ai` 服务骨架
- [x] 迁移 `reports` 服务到新位置

### Phase 3: 代码迁移（待执行）⏸️

#### 3.1 迁移 Ingestion 服务
```bash
# 从旧位置迁移
backend/device-ingestion/app/device_connector.py
  → src/backend/services/ingestion/device_connector.py

backend/device-ingestion/app/qc.py
  → src/backend/services/ingestion/qc.py

backend/device-ingestion/app/data_loader.py
  → src/backend/services/ingestion/parser.py
```

#### 3.2 迁移 Analysis 服务
```bash
backend/device-ingestion/app/analysis.py
  → src/backend/services/analysis/analyzer.py
  
# 将 ROI 相关功能拆分到独立模块
  → src/backend/services/analysis/roi.py
  → src/backend/services/analysis/thermal.py
```

#### 3.3 迁移 EMR 服务
```bash
backend/device-ingestion/app/emr.py
  → src/backend/services/emr/manager.py
  
backend/device-ingestion/app/data_platform.py
  → src/backend/repositories/emr_repository.py
```

#### 3.4 迁移 Treatment 服务
```bash
backend/device-ingestion/app/dispatch.py
  → src/backend/services/treatment/planner.py
  → src/backend/services/treatment/dispatcher.py
```

#### 3.5 迁移 AI 服务
```bash
backend/device-ingestion/app/llm_report.py
  → src/backend/services/ai/llm_report.py
```

#### 3.6 迁移数据模型
```bash
backend/device-ingestion/app/models.py
  → src/backend/models/schemas/
  → src/backend/models/domain/
```

#### 3.7 迁移 API 层
```bash
backend/device-ingestion/app/main.py
  → src/backend/api/main.py
  
# 将路由拆分到独立模块
  → src/backend/api/routes/ingestion.py
  → src/backend/api/routes/analysis.py
  → src/backend/api/routes/emr.py
  → src/backend/api/routes/reports.py
```

### Phase 4: 更新导入路径（待执行）

所有导入需要更新为新的模块路径：

```python
# 旧的导入 ❌
from app.config import DATA_DIR
from app.analysis import analyze_record
from app.emr import create_emr

# 新的导入 ✅
from src.backend.core.config import settings
from src.backend.services.analysis import AnalysisService
from src.backend.services.emr import EMRService

# 使用
analysis_service = AnalysisService()
result = analysis_service.analyze_record(record_id)
```

### Phase 5: 数据目录迁移（待执行）

```bash
# 移动大数据目录（9.2GB）
mv data storage/data
mv reports storage/reports
mv logs storage/logs
mv batch_results storage/logs/batch_results

# 创建符号链接向后兼容（可选）
ln -s storage/data data
ln -s storage/reports reports
ln -s storage/logs logs
```

### Phase 6: 脚本迁移（待执行）

```bash
# 移动脚本到规范位置
mv backend/device-ingestion/batch_generate_reports.py \
   scripts/data_processing/batch_generate_reports.py

mv backend/device-ingestion/fix_emr_patient_ids.py \
   scripts/data_processing/fix_emr_patient_ids.py

mv backend/device-ingestion/sync_patients_from_emr.py \
   scripts/data_processing/sync_patients_from_emr.py
```

---

## 配置系统升级

### 旧配置方式 ❌
```python
# backend/device-ingestion/app/config.py
import os
from pathlib import Path

DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
```

### 新配置方式 ✅
```python
# src/backend/core/config.py (已创建)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MYSQL_HOST: str = "localhost"
    DATA_DIR: Path = Path("storage/data")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

settings = get_settings()  # 单例

# 使用
from src.backend.core.config import settings
data_path = settings.DATA_DIR
```

### 环境配置优先级
1. 环境变量（最高）
2. `.env` 文件
3. `config/{ENVIRONMENT}.yaml`
4. `config/default.yaml`

---

## 测试策略

### 单元测试
```bash
# 测试单个服务
pytest tests/unit/services/test_analysis.py

# 测试核心功能
pytest tests/unit/core/test_config.py
```

### 集成测试
```bash
# 测试服务间集成
pytest tests/integration/test_emr_workflow.py
```

### 端到端测试
```bash
# 测试完整流程
pytest tests/e2e/test_full_workflow.py
```

---

## 向后兼容策略

为确保平滑过渡，保留旧的 `backend/` 目录作为兼容层：

1. 旧的 API 路径继续可用
2. 旧的导入路径通过桥接模块重定向
3. 数据目录通过符号链接兼容

**计划**：在 v2.0 完全删除旧代码。

---

## 依赖升级

### 新增依赖
- `pydantic-settings` - 配置管理
- `python-json-logger` - 结构化日志
- `prometheus-client` - 监控指标

### 安装
```bash
# 开发环境
pip install -r requirements/dev.txt

# 生产环境
pip install -r requirements/prod.txt
```

---

## 常见问题

### Q1: 为什么要重构？
**A**: 原有单体架构难以维护和扩展，重构后：
- 职责清晰，易于团队协作
- 模块独立，便于单元测试
- 配置规范，支持多环境部署

### Q2: 如何切换到新架构？
**A**: 
1. 拉取最新代码
2. 复制 `.env.example` 到 `.env` 并配置
3. 安装新依赖：`pip install -r requirements/dev.txt`
4. 运行迁移脚本：`make migrate`

### Q3: 旧代码何时删除？
**A**: 计划在新架构稳定运行 1 个月后（约 2026-04）删除。

### Q4: 如何贡献代码？
**A**: 
1. 新功能必须遵循新架构
2. 修bug可以在旧代码中，但建议同步到新架构
3. 参考 `docs/development/CONTRIBUTING.md`

---

## 下一步行动

### 立即执行（P0）
- [ ] 完成 Phase 3 代码迁移
- [ ] 更新所有导入路径
- [ ] 运行完整测试套件
- [ ] 更新部署文档

### 近期计划（P1）
- [ ] 实现 API 网关层
- [ ] 添加 Redis 缓存支持
- [ ] 实现分布式追踪
- [ ] 设置 CI/CD 流水线

### 长期规划（P2）
- [ ] 微服务拆分（可选）
- [ ] Kubernetes 部署
- [ ] 性能优化和监控
- [ ] 国际化支持

---

## 参考文档

- [架构优化方案](ARCHITECTURE_OPTIMIZATION.md)
- [配置管理指南](../development/CONFIGURATION.md)
- [API 文档](../api/README.md)
- [部署指南](../deployment/README.md)

---

**重构负责人**: AI Assistant  
**更新日期**: 2026-03-10  
**版本**: v1.0 → v2.0  
**状态**: 基础设施已完成，代码迁移待执行 ✅
