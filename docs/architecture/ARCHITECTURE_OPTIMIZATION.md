# EMR 项目架构优化方案

## 当前问题分析

### 1. 目录结构问题
- ❌ **数据目录混乱**：`data/`、`reports/`、`logs/`、`batch_results/` 散落在根目录
- ❌ **配置分散**：根目录 `config/`、backend 内部 `app/config.py` 混用
- ❌ **脚本杂乱**：`ingestion/` 下有多个顶层脚本（`batch_generate_reports.py`、`fix_emr_patient_ids.py` 等）
- ❌ **测试分散**：`tests/` 和 `tests/` 两处
- ❌ **缺少清晰分层**：`device-ingestion` 承担了过多职责

### 2. 架构问题
- ❌ **单体应用**：device-ingestion 包含数据接入、分析、报告、调度等多个职责
- ❌ **紧耦合**：报告生成依赖具体的数据接入层
- ❌ **缺少服务边界**：没有明确的领域边界

### 3. 可维护性问题
- ❌ **文档散乱**：12+ 个独立的 `.md` 文档在 device-ingestion 根目录
- ❌ **依赖管理混乱**：requirements.txt、pyproject.toml、requirements-dev.txt 混用
- ❌ **环境配置隐式**：配置硬编码在 Python 代码中

---

## 工业级标准架构方案

### 新目录结构（推荐）

```
emr/
├── .github/                    # GitHub Actions CI/CD
├── docs/                       # 统一文档目录
│   ├── architecture/           # 架构设计文档
│   ├── api/                    # API 文档
│   ├── deployment/             # 部署文档
│   ├── development/            # 开发指南
│   └── user-guide/             # 用户手册
│
├── src/                        # ⭐️ 源代码主目录
│   ├── backend/                # Python 后端服务
│   │   ├── api/                # API 网关层
│   │   │   ├── __init__.py
│   │   │   ├── main.py         # FastAPI 应用入口
│   │   │   ├── routes/         # 路由模块
│   │   │   └── middleware/     # 中间件
│   │   │
│   │   ├── services/           # ⭐️ 业务服务层（核心业务逻辑）
│   │   │   ├── ingestion/      # 数据接入服务
│   │   │   │   ├── __init__.py
│   │   │   │   ├── device_connector.py
│   │   │   │   ├── qc.py       # 质量控制
│   │   │   │   └── parser.py   # 数据解析
│   │   │   │
│   │   │   ├── analysis/       # 数据分析服务
│   │   │   │   ├── __init__.py
│   │   │   │   ├── analyzer.py
│   │   │   │   ├── roi.py      # ROI 分析
│   │   │   │   └── thermal.py  # 温度分析
│   │   │   │
│   │   │   ├── reports/        # 报告生成服务（已完成）
│   │   │   │   ├── __init__.py
│   │   │   │   ├── docx_generator.py
│   │   │   │   └── template_generator.py
│   │   │   │
│   │   │   ├── emr/            # EMR（电子病历）服务
│   │   │   │   ├── __init__.py
│   │   │   │   ├── manager.py
│   │   │   │   └── patient.py
│   │   │   │
│   │   │   ├── treatment/      # 治疗方案服务
│   │   │   │   ├── __init__.py
│   │   │   │   ├── planner.py
│   │   │   │   └── dispatcher.py
│   │   │   │
│   │   │   └── ai/             # AI 增强服务
│   │   │       ├── __init__.py
│   │   │       ├── llm_report.py
│   │   │       └── rag.py      # RAG 检索增强
│   │   │
│   │   ├── core/               # ⭐️ 核心层（基础设施）
│   │   │   ├── __init__.py
│   │   │   ├── config.py       # 统一配置管理
│   │   │   ├── database.py     # 数据库连接
│   │   │   ├── storage.py      # 存储抽象
│   │   │   ├── logging.py      # 日志配置
│   │   │   └── exceptions.py   # 自定义异常
│   │   │
│   │   ├── models/             # 数据模型层
│   │   │   ├── __init__.py
│   │   │   ├── domain/         # 领域模型
│   │   │   ├── schemas/        # Pydantic 模型
│   │   │   └── entities/       # ORM 实体
│   │   │
│   │   ├── repositories/       # ⭐️ 数据访问层
│   │   │   ├── __init__.py
│   │   │   ├── emr_repository.py
│   │   │   ├── patient_repository.py
│   │   │   └── report_repository.py
│   │   │
│   │   └── utils/              # 工具函数
│   │       ├── __init__.py
│   │       ├── datetime.py
│   │       └── validators.py
│   │
│   └── web/               # Next.js 前端应用
│       ├── src/
│       ├── public/
│       └── package.json
│
├── config/                     # ⭐️ 统一配置目录
│   ├── default.yaml            # 默认配置
│   ├── development.yaml        # 开发环境
│   ├── production.yaml         # 生产环境
│   ├── test.yaml               # 测试环境
│   └── treatment_rules.yaml    # 业务规则
│
├── scripts/                    # ⭐️ 脚本与工具
│   ├── db/                     # 数据库脚本
│   │   ├── migrations/         # 数据迁移
│   │   └── seeds/              # 测试数据
│   ├── deployment/             # 部署脚本
│   ├── data_processing/        # 数据处理工具
│   │   ├── batch_generate_reports.py
│   │   └── fix_emr_patient_ids.py
│   └── build/                  # 构建脚本
│
├── tests/                      # ⭐️ 测试目录
│   ├── unit/                   # 单元测试
│   ├── integration/            # 集成测试
│   ├── e2e/                    # 端到端测试
│   ├── fixtures/               # 测试数据
│   └── conftest.py             # pytest 配置
│
├── storage/                    # ⭐️ 运行时数据存储（不提交到 Git）
│   ├── data/                   # 原始数据（9.2GB）
│   ├── reports/                # 生成的报告
│   ├── logs/                   # 应用日志
│   ├── cache/                  # 缓存文件
│   └── uploads/                # 用户上传
│
├── rag/                        # RAG 知识库
│   ├── dataset/                # 原始文档
│   └── kb/                     # 向量数据库
│
├── docker/                     # Docker 相关文件
│   ├── backend.Dockerfile
│   ├── web.Dockerfile
│   └── nginx.conf
│
├── .env.example                # 环境变量模板
├── .gitignore
├── docker-compose.yml          # 本地开发环境
├── docker-compose.prod.yml     # 生产环境
├── Makefile                    # 项目任务管理
├── pyproject.toml              # Python 项目配置
├── README.md                   # 项目主文档
└── requirements/               # ⭐️ 依赖管理
    ├── base.txt                # 基础依赖
    ├── dev.txt                 # 开发依赖
    └── prod.txt                # 生产依赖
```

---

## 分层架构设计

### 1. API 层（Presentation Layer）
**职责**：HTTP 请求处理、参数验证、响应格式化
- `src/backend/api/routes/` - 路由定义
- `src/backend/api/middleware/` - 认证、日志、异常处理

### 2. 服务层（Service Layer）
**职责**：业务逻辑、流程编排
- `services/ingestion/` - 设备数据接入
- `services/analysis/` - 数据分析与ROI检测
- `services/reports/` - 报告生成（已重构）
- `services/emr/` - 电子病历管理
- `services/treatment/` - 治疗方案规划
- `services/ai/` - AI增强功能

### 3. 仓储层（Repository Layer）
**职责**：数据持久化、查询抽象
- 统一数据访问接口
- 支持多种存储后端（MySQL、ClickHouse、文件系统）

### 4. 核心层（Core Layer）
**职责**：基础设施、配置、日志
- 配置管理（支持环境变量覆盖）
- 统一日志格式
- 异常处理机制

---

## 配置管理优化

### 环境配置层级（Environment Hierarchy）
```python
# src/backend/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # 环境标识
    ENVIRONMENT: str = "development"
    
    # 应用配置
    APP_NAME: str = "EMR System"
    API_VERSION: str = "v1"
    DEBUG: bool = False
    
    # 数据库配置
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "emr_user"
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str = "emr_db"
    
    # 存储路径
    STORAGE_ROOT: Path = Path("storage")
    DATA_DIR: Path = STORAGE_ROOT / "data"
    REPORTS_DIR: Path = STORAGE_ROOT / "reports"
    LOGS_DIR: Path = STORAGE_ROOT / "logs"
    
    # AI 配置
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "qwen2.5:14b"
    LLM_BASE_URL: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """单例配置获取"""
    return Settings()
```

### 配置文件优先级
1. 环境变量（最高优先级）
2. `.env` 文件
3. `config/{environment}.yaml`
4. `config/default.yaml`（默认值）

---

## 依赖管理优化

### requirements/ 目录结构
```bash
requirements/
├── base.txt          # 核心依赖
├── dev.txt           # 开发工具（包含 base.txt）
└── prod.txt          # 生产优化（包含 base.txt）
```

**base.txt**：
```
fastapi==0.110.0
uvicorn[standard]==0.27.0
pydantic==2.6.1
pydantic-settings==2.1.0
python-docx==1.1.0
matplotlib==3.8.2
mysql-connector-python==8.3.0
clickhouse-driver==0.2.6
PyYAML==6.0.1
```

**dev.txt**：
```
-r base.txt
pytest==8.0.0
pytest-cov==4.1.0
pytest-asyncio==0.23.5
black==24.2.0
ruff==0.2.1
mypy==1.8.0
httpx==0.26.0
```

---

## 迁移步骤（渐进式重构）

### Phase 1: 基础架构调整 ✅
- [x] 创建 `src/backend/` 目录
- [x] 重构 reports 模块到 `src/backend/services/reports/`
- [ ] 创建统一配置管理 `src/backend/core/config.py`
- [ ] 建立 `storage/` 目录并迁移数据文件

### Phase 2: 服务拆分（本周）
- [ ] 拆分 ingestion 服务
- [ ] 拆分 analysis 服务
- [ ] 拆分 emr 服务
- [ ] 建立 repository 层

### Phase 3: API 重构（下周）
- [ ] 创建统一 API 网关
- [ ] 实现路由模块化
- [ ] 添加认证中间件

### Phase 4: 测试与文档（持续）
- [ ] 迁移并补充单元测试
- [ ] 编写集成测试
- [ ] 更新 API 文档

---

## 即将执行的操作

### 1. 创建新目录结构
```bash
# 创建 src/ 主目录
mkdir -p src/backend/{api,services,core,models,repositories,utils}
mkdir -p src/backend/api/{routes,middleware}
mkdir -p src/backend/services/{ingestion,analysis,emr,treatment,ai}
mkdir -p src/backend/models/{domain,schemas,entities}

# 创建配置目录
mkdir -p config requirements

# 创建存储目录
mkdir -p storage/{data,reports,logs,cache,uploads}

# 创建测试目录
mkdir -p tests/{unit,integration,e2e,fixtures}
```

### 2. 移动现有文件
```bash
# 移动 reports 模块（已完成）
# reports/ → src/backend/services/reports/

# 移动数据目录
mv data storage/data
mv reports storage/reports
mv logs storage/logs
mv batch_results storage/logs/batch_results

# 移动脚本
mv ingestion/*.py scripts/data_processing/

# 合并配置
mv config config.old
# 创建新的 config/ 结构
```

### 3. 更新导入路径
- 更新所有模块的 import 语句
- 修改 `sys.path` 配置
- 更新 `pyproject.toml`

### 4. 配置文件迁移
- 创建 `.env.example`
- 将 `config.py` 中的值迁移到 YAML
- 实现环境配置加载器

---

## 预期收益

### 开发效率提升
- ✅ **清晰的职责划分**：每个模块职责单一
- ✅ **易于扩展**：新增服务只需添加对应目录
- ✅ **测试友好**：清晰的依赖关系便于 mock

### 运维效率提升
- ✅ **环境隔离**：development/test/production 配置分离
- ✅ **日志集中**：统一的日志目录和格式
- ✅ **容器化友好**：符合 Docker 最佳实践

### 团队协作提升
- ✅ **降低认知负担**：标准化的目录结构
- ✅ **减少冲突**：模块隔离减少代码冲突
- ✅ **文档完善**：集中的文档管理

---

## 参考标准

本方案参考以下工业标准：
- **Django Project Structure** - 服务分层
- **DDD (Domain-Driven Design)** - 领域驱动设计
- **Clean Architecture** - 依赖反转原则
- **12-Factor App** - 配置管理最佳实践
- **Poetry/PDM** - 现代 Python 依赖管理

---

## 下一步行动

请确认是否开始执行架构重构？我将：

1. ✅ 创建新的目录结构
2. ✅ 移动 reports 模块（已完成）
3. ⏳ 创建统一配置管理
4. ⏳ 迁移数据存储目录
5. ⏳ 更新所有导入路径
6. ⏳ 更新文档和 README

预计影响：
- 🟡 需要更新部署脚本
- 🟡 需要更新 CI/CD 配置
- 🟡 需要通知团队成员更新本地环境
