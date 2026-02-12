# 项目管理方法论

## 一、思路清晰 (Clarity of Thinking)

### 1. 项目目标分解
**顶层目标**: 构建医院患者管理和诊疗平台

**分层目标**:
```
1. 核心业务流程
   ├─ 患者管理 (患者注册、信息维护、查询)
   ├─ 医学影像处理 (设备上传、图像分析、数据存储)
   ├─ 电子病历 (EMR生成、管理、归档)
   ├─ 诊疗决策 (诊断分析、治疗方案生成)
   └─ 报告管理 (报告生成、预览、打印、下载)

2. 支撑能力
   ├─ 用户认证与授权
   ├─ 数据持久化 (MySQL)
   ├─ 文件存储 (本地/云存储)
   ├─ API接口体系
   └─ 前后端通信
```

### 2. 决策过程记录
每个重要决策都应该记录 **Why-What-How**:

**Why (为什么)**
- 问题：为什么需要这个功能？
- 用户需求：解决什么用户问题？
- 业务价值：带来什么商业价值？

**What (做什么)**
- 功能范围：功能边界是什么？
- 交付物：包括哪些技术产物？
- 验收标准：如何判断完成？

**How (怎么做)**
- 技术方案：采用什么技术栈？
- 实现步骤：分几个阶段？
- 风险对策：可能遇到什么问题？

### 3. 知识库建设
```
docs/
├─ ARCHITECTURE.md          # 系统架构设计
├─ API_SPECIFICATION.md     # API规范文档
├─ DATABASE_SCHEMA.md       # 数据库设计
├─ FEATURE_DECISIONS.md     # 功能决策记录
├─ TROUBLESHOOTING.md       # 常见问题解决方案
└─ LEARNING_NOTES.md        # 学习笔记
```

---

## 二、需求清晰 (Requirements Clarity)

### 1. 需求的三个层次

#### L1: 用户故事 (User Story)
```
作为 <角色>
我想要 <功能>
以便 <业务价值>

例子:
作为 医生
我想要 看到患者的历史报告
以便 进行对比诊断
```

#### L2: 验收标准 (Acceptance Criteria)
```
GIVEN <前置条件>
WHEN <用户操作>
THEN <预期结果>

例子:
GIVEN 患者已注册并有报告
WHEN 点击"查看报告"按钮
THEN 显示报告列表和预览选项
```

#### L3: 技术需求 (Technical Requirement)
```
- API端点: GET /patients/{id}/reports
- 请求参数: date_from, date_to
- 响应格式: JSON array of ReportFile
- 性能指标: <200ms 响应时间
- 错误处理: 404, 401, 500
```

### 2. 需求追踪矩阵

```markdown
| 功能模块 | 用户故事 | 是否实现 | 验收标准 | 是否通过 | 优先级 |
|---------|--------|--------|--------|--------|------|
| 患者管理 | 注册患者 | ✅ | 能创建患者记录 | ✅ | P0 |
|         | 查询患者 | ✅ | 能搜索患者 | ✅ | P0 |
|         | 编辑患者 | ❌ | - | - | P1 |
| 报告管理 | 上传报告 | ✅ | 能保存文件 | ✅ | P0 |
|         | 预览报告 | ✅ | 显示DOCX | ✅ | P0 |
|         | 打印报告 | ✅ | 打开打印对话框 | ✅ | P1 |
```

### 3. 需求优先级体系

| 优先级 | 含义 | 交付时机 | 示例 |
|------|-----|--------|------|
| P0 (Critical) | 功能缺失则系统无法使用 | MVP必须 | 患者注册、EMR生成 |
| P1 (High) | 重要功能，直接影响体验 | V1.0 必须 | 报告预览、打印 |
| P2 (Medium) | 有用的功能，可以后续补充 | V1.x 推荐 | 批量操作、高级搜索 |
| P3 (Low) | 锦上添花的功能 | 没有时间压力 | 深色主题、数据导出 |

---

## 三、结构清晰 (Architecture Clarity)

### 1. 代码组织结构

```
hospital-report/
├── frontend/                 # Next.js 15 前端应用
│   ├── src/
│   │   ├── app/             # App Router 路由
│   │   │   ├── patients/    # 患者管理页面
│   │   │   ├── emr/         # 电子病历页面
│   │   │   ├── treatment/   # 治疗方案页面
│   │   │   └── upload/      # 设备上传页面
│   │   ├── components/      # 可复用组件
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── types/           # TypeScript 类型定义
│   │   └── utils/           # 工具函数
│   └── package.json
│
├── backend/                 # FastAPI 后端服务
│   ├── device-ingestion/
│   │   └── app/
│   │       ├── main.py              # 应用入口 + 路由定义
│   │       ├── config.py            # 配置管理
│   │       ├── models.py            # 数据模型
│   │       ├── data_platform.py     # 数据访问层
│   │       ├── analysis.py          # 业务逻辑层
│   │       ├── emr.py               # EMR处理
│   │       ├── device_connector.py  # 设备连接
│   │       └── qc.py                # 质量检查
│   └── requirements.txt
│
├── docs/                    # 文档
│   ├── ARCHITECTURE.md      # 系统架构
│   ├── API_SPECIFICATION.md # API规范
│   ├── DATABASE_SCHEMA.md   # 数据库设计
│   ├── PROJECT_METHODOLOGY.md # 项目方法论
│   └── project-mindmap.md   # 项目思维导图
│
└── README.md                # 项目总览
```

### 2. 分层架构

```
┌─────────────────────────────────────────────────────┐
│         Presentation Layer (前端展示层)              │
│   ├─ Pages (患者、EMR、治疗、上传页面)              │
│   ├─ Components (表单、模态框、表格组件)            │
│   └─ Hooks (状态管理、localStorage持久化)          │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP/REST
┌──────────────────────▼──────────────────────────────┐
│         API Layer (接口层)                          │
│   ├─ GET /patients (获取患者列表)                   │
│   ├─ POST /patients (创建患者)                      │
│   ├─ GET /emr (获取EMR列表)                        │
│   ├─ POST /emr/generate (生成EMR)                  │
│   └─ GET /reports (获取报告列表)                   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│      Business Logic Layer (业务逻辑层)              │
│   ├─ analysis.py (诊断分析)                        │
│   ├─ emr.py (EMR生成管理)                          │
│   ├─ dispatch.py (数据分发)                        │
│   └─ qc.py (质量检查)                              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│      Data Access Layer (数据访问层)                 │
│   ├─ data_platform.py (数据库操作)                 │
│   ├─ storage.py (文件存储)                         │
│   └─ device_connector.py (设备数据读取)            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│      Data Layer (数据层)                            │
│   ├─ MySQL (患者、EMR、记录数据)                   │
│   ├─ File System (报告、图像文件)                  │
│   └─ Device Storage (设备数据)                     │
└─────────────────────────────────────────────────────┘
```

### 3. 数据流设计

```
患者工作流:
患者注册 → 设备上传 → 数据分析 → EMR生成 → 诊断分析 → 治疗方案 → 报告生成

数据流向:
Frontend (React) 
  → POST /ingest (上传数据)
    → device_connector (解析设备数据)
      → analysis (分析图像)
        → data_platform (存储分析结果)
          → MySQL (患者、记录、EMR表)
            → File System (报告文件)
              ← GET /reports (获取列表)
                ← Frontend (前端显示)
```

### 4. 状态管理设计

```
前端状态分类:

1. UI State (UI状态)
   - 模态框显示/隐藏
   - 表单是否打开
   - 预览窗口显示
   
2. Data State (数据状态)
   - 患者列表
   - EMR记录
   - 报告文件
   
3. Flow State (流程状态) - 使用 localStorage 持久化
   - currentPatientId (当前患者)
   - searchQuery (搜索条件)
   - emrContext (来自EMR的诊断信息)
   
存储策略:
- UI State: React useState (仅内存)
- Data State: React useState (仅内存) + 必要时从API刷新
- Flow State: localStorage (持久化) + React useState (运行时)
```

---

## 四、工作流程 (Workflow)

### 1. 日常开发流程

```
1. 需求理解
   ✓ 阅读用户故事和验收标准
   ✓ 理解技术需求和API设计
   ✓ 确认交付标准

2. 设计阶段
   ✓ 确认影响范围
   ✓ 设计前端UI/UX
   ✓ 设计后端API和数据库
   ✓ 制定测试计划

3. 实现阶段
   ✓ 后端优先 (API + 数据库)
   ✓ 前端实现 (集成API)
   ✓ 集成测试
   ✓ 本地验证

4. 交付阶段
   ✓ 代码审查
   ✓ 更新文档
   ✓ 创建提交记录
   ✓ 更新需求矩阵
```

### 2. 代码审查清单

```
代码质量:
- [ ] 没有语法错误和编译警告
- [ ] 遵循代码规范和最佳实践
- [ ] 有适当的错误处理
- [ ] 有必要的日志记录

功能完整性:
- [ ] 实现了所有验收标准
- [ ] 处理了边界情况
- [ ] 支持了国际化/本地化
- [ ] 考虑了性能影响

文档完整性:
- [ ] API文档已更新
- [ ] 数据库变更已记录
- [ ] 代码注释清晰
- [ ] 部署指南已更新

测试完整性:
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 手动测试验证
- [ ] 性能测试检查
```

---

## 五、常见问题解决 (Troubleshooting)

### 问题：需求在开发中不断变化

**解决方案**:
1. 建立需求变更控制流程
2. 评估变更的影响范围和成本
3. 更新需求文档和优先级
4. 与利益相关者沟通确认
5. 更新项目计划和时间表

### 问题：不知道下一步做什么

**解决方案**:
1. 检查需求追踪矩阵，找 P0 优先级未完成项
2. 参考项目思维导图，找清晰的功能边界
3. 查看 TODO 列表
4. 咨询PM或业务方确认优先级

### 问题：代码结构混乱

**解决方案**:
1. 严格遵循分层架构
2. 定期重构降低耦合度
3. 使用代码规范工具 (eslint, prettier)
4. 进行代码审查和知识分享

---

## 六、度量与改进 (Metrics & Improvement)

### 1. 项目度量

| 指标 | 说明 | 目标值 | 当前值 |
|-----|-----|------|------|
| 需求完成率 | 已完成需求数/总需求数 | 100% | - |
| 缺陷密度 | 缺陷数/代码行数 | <0.5% | - |
| 代码覆盖率 | 测试覆盖的代码比例 | >80% | - |
| 平均响应时间 | API平均响应时间 | <200ms | - |
| 上线准时率 | 按时完成的功能比例 | >90% | - |

### 2. 定期回顾 (Retrospective)

**每周进行**:
- 本周完成了什么?
- 遇到了什么障碍?
- 下周的优先级是什么?
- 需要什么支持?

**每月进行**:
- 本月的目标完成情况
- 代码质量评估
- 技术债务盘点
- 改进计划制定

---

## 七、最佳实践 (Best Practices)

### 1. 命名规范

```
文件/文件夹命名:
- 使用英文小写，用 - 分隔
- 例: patient-list.tsx, emr-service.py

变量/函数命名:
- 前端: camelCase (handleSubmit, patientList)
- 后端: snake_case (handle_submit, patient_list)

数据库字段命名:
- 小写 + 下划线 (patient_id, created_at)

API端点命名:
- 资源名词 + HTTP方法
- 例: GET /patients, POST /patients, GET /patients/{id}
```

### 2. 注释规范

```
为什么要注释:
✓ 解释复杂的业务逻辑
✓ 记录重要的决策和为什么
✓ 标记TODO/FIXME/HACK

什么时候不需要注释:
✗ 注释不要重复代码
✗ 注释不要和代码不同步
✗ 不要过度注释明显的代码
```

### 3. 提交规范

```
提交信息格式:
<type>(<scope>): <subject>

<body>

<footer>

例子:
feat(patients): add infinite scroll for patient list

- Implement pagination with page and limit parameters
- Add scroll listener to detect bottom of page
- Show loading indicator while fetching more data
- Display "all data loaded" message when complete

Fixes #123
```

---

## 八、快速参考 (Quick Reference)

### 开发新功能的步骤

1. **需求梳理** (30 min)
   - [ ] 写出用户故事
   - [ ] 列出验收标准
   - [ ] 更新需求追踪矩阵

2. **设计阶段** (1-2 h)
   - [ ] 设计API端点
   - [ ] 设计数据库变更
   - [ ] 设计前端UI组件

3. **后端实现** (2-4 h)
   - [ ] 创建数据库表/字段
   - [ ] 实现API端点
   - [ ] 添加错误处理
   - [ ] 编写测试

4. **前端实现** (2-4 h)
   - [ ] 创建页面/组件
   - [ ] 调用API接口
   - [ ] 处理加载/错误状态
   - [ ] 编写测试

5. **测试验证** (1-2 h)
   - [ ] 功能测试
   - [ ] 边界情况测试
   - [ ] 性能测试
   - [ ] 兼容性测试

6. **文档更新** (30 min)
   - [ ] 更新API文档
   - [ ] 更新数据库文档
   - [ ] 更新项目思维导图

---

## 总结

**思路清晰** = 明确的目标分解 + 完整的决策记录 + 系统的知识库
**需求清晰** = 多层次的需求表述 + 可追踪的需求管理 + 明确的优先级
**结构清晰** = 严格的分层架构 + 明确的代码组织 + 完善的数据流设计

坚持这些原则，您的项目将更加有序、可维护性更强！
