# 项目重构计划

## 当前问题总结

### 🔴 严重问题
1. **后端平铺架构** - 所有代码在 `app/` 下无分层
2. **文件过大** - 多个文件超过400行
3. **前端组件超大** - 最大1442行单文件
4. **缺少测试** - 0%测试覆盖率
5. **缺少容器化** - 无Dockerfile

### ⚠️ 一般问题  
6. 缺少CI/CD流程
7. 缺少日志和监控
8. 缺少API文档生成
9. 缺少环境变量管理
10. 缺少代码规范检查

---

## 📋 重构路线图

### 阶段1: 基础设施（2-3天）

#### 1.1 添加容器化支持
- [ ] 创建后端 Dockerfile
- [ ] 创建前端 Dockerfile  
- [ ] 创建 docker-compose.yml
- [ ] 添加 .env.example

#### 1.2 添加测试框架
- [ ] 配置 pytest (后端)
- [ ] 配置 Jest (前端)
- [ ] 添加基础测试用例
- [ ] 配置覆盖率报告

#### 1.3 添加CI/CD
- [ ] GitHub Actions工作流
- [ ] 自动化测试
- [ ] 代码质量检查 (ruff, eslint)
- [ ] 自动化部署

---

### 阶段2: 后端重构（5-7天）

#### 2.1 目标目录结构
```
emr/
├── src/                          # 源代码
│   ├── api/                      # API路由层
│   │   ├── __init__.py
│   │   ├── deps.py              # 依赖注入
│   │   └── v1/                  # API版本
│   │       ├── __init__.py
│   │       ├── patients.py      # 患者路由
│   │       ├── emr.py           # EMR路由
│   │       ├── records.py       # 记录路由
│   │       └── reports.py       # 报告路由
│   │
│   ├── core/                     # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py            # 配置管理
│   │   ├── security.py          # 安全配置
│   │   └── logging.py           # 日志配置
│   │
│   ├── models/                   # 数据模型
│   │   ├── __init__.py
│   │   ├── domain/              # 领域模型
│   │   │   ├── patient.py
│   │   │   ├── emr.py
│   │   │   └── record.py
│   │   └── schemas/             # Pydantic schemas
│   │       ├── patient.py
│   │       ├── emr.py
│   │       └── record.py
│   │
│   ├── services/                 # 业务逻辑
│   │   ├── __init__.py
│   │   ├── patient_service.py
│   │   ├── emr_service.py
│   │   ├── analysis_service.py
│   │   ├── report_service.py
│   │   └── device_service.py
│   │
│   ├── repositories/             # 数据访问层
│   │   ├── __init__.py
│   │   ├── base.py              # 基础仓库
│   │   ├── patient_repo.py
│   │   ├── emr_repo.py
│   │   └── record_repo.py
│   │
│   ├── utils/                    # 工具函数
│   │   ├── __init__.py
│   │   ├── qc.py
│   │   ├── image_processing.py
│   │   └── file_handler.py
│   │
│   └── main.py                   # 应用入口
│
├── tests/                        # 测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── alembic/                      # 数据库迁移
│   └── versions/
│
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

#### 2.2 重构步骤
1. **创建新目录结构**（不影响现有代码）
2. **提取路由层**（从main.py拆分）
3. **创建服务层**（拆分业务逻辑）
4. **创建仓储层**（数据访问抽象）
5. **迁移测试验证**
6. **删除旧代码**

---

### 阶段3: 前端重构（5-7天）

#### 3.1 目标目录结构
```
web/
├── src/
│   ├── app/                      # Next.js App Router
│   │   ├── (auth)/              # 认证路由组
│   │   │   └── login/
│   │   ├── (dashboard)/         # 主要功能路由组
│   │   │   ├── patients/
│   │   │   ├── emr/
│   │   │   ├── upload/
│   │   │   ├── treatment/
│   │   │   └── layout.tsx
│   │   ├── layout.tsx
│   │   └── page.tsx
│   │
│   ├── components/               # 可复用组件
│   │   ├── ui/                  # UI基础组件
│   │   │   ├── Button.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Table.tsx
│   │   │   └── Form/
│   │   ├── features/            # 功能组件
│   │   │   ├── PatientList/
│   │   │   ├── EmrEditor/
│   │   │   ├── ReportViewer/
│   │   │   └── DataUploader/
│   │   └── layouts/             # 布局组件
│   │
│   ├── hooks/                    # 自定义Hooks
│   │   ├── usePatients.ts
│   │   ├── useEmr.ts
│   │   ├── useLocalStorage.ts
│   │   └── useApi.ts
│   │
│   ├── lib/                      # 工具库
│   │   ├── api/                 # API客户端
│   │   │   ├── client.ts
│   │   │   ├── patients.ts
│   │   │   ├── emr.ts
│   │   │   └── reports.ts
│   │   ├── utils/               # 工具函数
│   │   │   ├── format.ts
│   │   │   ├── validation.ts
│   │   │   └── constants.ts
│   │   └── types/               # TypeScript类型
│   │       ├── patient.ts
│   │       ├── emr.ts
│   │       └── api.ts
│   │
│   └── styles/                   # 样式
│       └── globals.css
│
├── __tests__/                    # 测试
│   ├── components/
│   ├── hooks/
│   └── integration/
│
├── public/
├── Dockerfile
├── next.config.ts
├── jest.config.js
└── package.json
```

#### 3.2 组件拆分示例
```tsx
// 当前: patients/page.tsx (1238行)
// 重构为:

app/patients/page.tsx (100行)           ← 页面容器
components/features/PatientList/ (200行) ← 列表组件
  ├── PatientList.tsx
  ├── PatientTable.tsx
  ├── PatientFilters.tsx
  └── types.ts
components/features/PatientForm/ (150行) ← 表单组件
  ├── PatientForm.tsx
  ├── BasicInfo.tsx
  ├── MedicalHistory.tsx
  └── validation.ts
components/features/PatientDetail/ (100行) ← 详情组件
components/ui/Modal.tsx (50行)            ← 通用模态框
hooks/usePatients.ts (80行)              ← 数据逻辑
lib/api/patients.ts (50行)               ← API调用
```

---

### 阶段4: 生产环境完善（3-5天）

#### 4.1 安全性
- [ ] 添加JWT认证
- [ ] 添加RBAC权限控制
- [ ] 添加请求限流
- [ ] 添加SQL注入防护
- [ ] 添加HTTPS支持

#### 4.2 可观测性
- [ ] 结构化日志（JSON格式）
- [ ] 集成Prometheus指标
- [ ] 健康检查端点
- [ ] 性能追踪
- [ ] 错误监控（Sentry）

#### 4.3 性能优化
- [ ] 数据库索引优化
- [ ] API响应缓存
- [ ] 前端代码分割
- [ ] 图片懒加载
- [ ] CDN配置

#### 4.4 文档
- [ ] OpenAPI/Swagger文档
- [ ] 数据库ER图
- [ ] 部署文档
- [ ] 运维手册

---

## 📊 重构优先级评分

| 任务 | 优先级 | 影响 | 工作量 | 建议顺序 |
|------|--------|------|--------|---------|
| Docker化 | P0 | 高 | 1天 | 1 |
| 后端分层 | P0 | 高 | 5天 | 2 |
| 添加测试 | P0 | 高 | 3天 | 3 |
| 前端组件化 | P1 | 中 | 5天 | 4 |
| CI/CD | P1 | 中 | 2天 | 5 |
| 日志监控 | P2 | 中 | 2天 | 6 |
| 安全加固 | P2 | 高 | 3天 | 7 |

---

## 🚀 快速开始

### 1. 创建Docker环境（今天就可以做）

```bash
# 创建后端Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# 创建docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  mysql:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: hospital
      MYSQL_DATABASE: hospital
      MYSQL_USER: hospital
      MYSQL_PASSWORD: hospital
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./database/init_mysql.sql:/docker-entrypoint-initdb.d/init.sql

  backend:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - mysql
    environment:
      - MYSQL_HOST=mysql
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./reports:/app/reports

  web:
    build: ./web
    ports:
      - "3000:3000"
    depends_on:
      - backend
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000

volumes:
  mysql_data:
EOF
```

### 2. 添加环境变量管理

```bash
# 创建 .env.example
cat > .env.example << 'EOF'
# Database
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DB=hospital
MYSQL_USER=hospital
MYSQL_PASSWORD=hospital

# API
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false

# Web
NEXT_PUBLIC_API_URL=http://localhost:8000

# Security
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION=3600
EOF
```

---

## 💡 立即可执行的改进清单

### 今天（2小时内）
- [x] 完成结构分析
- [ ] 创建 REFACTOR_PLAN.md
- [ ] 创建 docker-compose.yml
- [ ] 创建 .env.example
- [ ] 创建 .dockerignore

### 本周（每天2-3小时）
- [ ] 后端添加tests/目录和pytest配置
- [ ] 前端添加__tests__/目录和jest配置
- [ ] 编写第一个单元测试
- [ ] 配置GitHub Actions
- [ ] 重构main.py拆分路由

### 下周
- [ ] 开始后端分层重构
- [ ] 开始前端组件拆分
- [ ] 添加API文档

---

## 📚 参考资源

### 后端最佳实践
- [FastAPI最佳实践](https://github.com/zhanymkanov/fastapi-best-practices)
- [Clean Architecture Python](https://github.com/cosmic-python/book)
- [12-Factor App](https://12factor.net/)

### 前端最佳实践
- [Next.js项目结构](https://nextjs.org/docs/app/building-your-application)
- [React组件设计模式](https://www.patterns.dev/)
- [前端架构指南](https://github.com/elsewhencode/project-guidelines)
