# 后端结构重构迁移完成

## 📋 迁移内容

### 目录结构变更

**旧结构**：
```
src/
  backend/
    ├── core/
    ├── api/
    ├── services/
    ├── models/
    ├── repositories/
    └── utils/
```

**新结构**：
```
backend/           ← 现在直接在项目根目录
  ├── core/
  ├── api/
  ├── services/
  ├── models/
  ├── repositories/
  └── utils/

src/               ← 现在只有空的 __init__.py（保留兼容性）
  └── __init__.py
```

## 🔄 所有变更明细

### 1️⃣ 后端代码迁移
- ✅ 复制 `src/backend` → `backend`
- ✅ 删除旧的 `src/backend` 目录

### 2️⃣ Python 导入路径更新
**文件数**: 11 个（32 处导入）

所有文件中的导入从：
```python
from src.backend.core import ...
from src.backend.services import ...
```

改为：
```python
from backend.core import ...
from backend.services import ...
```

更新文件：
- `backend/api/main.py`
- `backend/api/routes/*.py` (6 个路由文件)
- `backend/services/*/__init__.py` (6 个服务文件)

### 3️⃣ 相对路径调整
**backend/services** 中的 `_LEGACY_BACKEND_DIR` 配置：

从 `parents[4]` → `parents[3]` （少一层 src 目录）

受影响文件：
- `backend/services/ingestion/__init__.py`
- `backend/services/analysis/__init__.py`
- `backend/services/emr/__init__.py`
- `backend/services/ai/__init__.py`
- `backend/services/treatment/__init__.py`
- `backend/services/platform/__init__.py`

### 4️⃣ 启动脚本更新

#### Makefile
```makefile
# 旧：
exec $(VENV_PY) -m uvicorn src.backend.api.main:app ...

# 新：
exec $(VENV_PY) -m uvicorn backend.api.main:app ...
```

#### Dockerfile
```dockerfile
# 旧：
COPY device-ingestion/ .
CMD ["uvicorn", "app.main:app", ...]

# 新：
COPY backend/ ./backend/
COPY ingestion/ ./ingestion/
COPY src/ ./src/
CMD ["uvicorn", "backend.api.main:app", ...]
```

#### ingestion/app/main.py (兼容层)
```python
# 旧：
_new_api_main = importlib.import_module("src.backend.api.main")

# 新：
_new_api_main = importlib.import_module("backend.api.main")
```

## ✅ 验证检查表

- [x] 所有 Python 导入路径已更新
- [x] 相对路径已调整
- [x] Makefile 启动命令已更新
- [x] Dockerfile 已更新
- [x] 兼容层已更新
- [x] 所有后端模块语法检查通过
- [x] 导入测试成功
- [x] 旧代码已清理（删除 src/backend）

## 🚀 立即使用

### 本地开发
```bash
make install  # 安装依赖
make service  # 启动后端服务（使用新的 backend.api.main）
make web      # 启动前端
```

### Docker 部署
```bash
docker-compose -f docker/docker-compose.yml up -d
# Dockerfile 会自动使用新的 backend 结构
```

## 📝 文档待更新项
文档中仍有旧的导入路径示例（不影响运行）：
- `docs/architecture/MIGRATION_GUIDE.md`
- `docs/REFACTOR_PLAN.md`

这些可以视需要后续更新。

## 🔗 关键路径映射

| 旧路径 | 新路径 |
|--------|--------|
| `src.backend.core` | `backend.core` |
| `src.backend.api` | `backend.api` |
| `src.backend.services` | `backend.services` |
| `src.backend.models` | `backend.models` |
| `src/backend/api/main.py:app` | `backend/api/main.py:app` |

## 💡 技术细节

### sys.path 处理
Python 虽然在 backend/services 中修改了相对路径 `parents[3]` 而不是 `parents[4]`，但由于：
1. Makefile 和 docker-compose 都在项目根目录运行
2. PYTHONPATH 会自动包含项目根目录
3. uvicorn 启动时会正确加载 backend 模块

所以导入不会有问题。

## ⚠️ 兼容性说明
- ✅ 旧的 `ingestion/app/main.py` 兼容层仍可用
- ✅ 所有旧的 device-ingestion 代码仍保留
- ✅ 可以继续使用 `uvicorn app.main:app` 启动（通过兼容层）

