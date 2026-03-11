# 系统架构设计文档

## 一、系统总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Client Layer                          │
│                   (Web Browser)                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │    Next.js 15 Frontend Application              │   │
│  │  ├─ React 19 Components                         │   │
│  │  ├─ TypeScript Type System                      │   │
│  │  ├─ TailwindCSS Styling                         │   │
│  │  └─ localStorage State Persistence              │   │
│  └─────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP/REST/JSON
┌──────────────────▼──────────────────────────────────────┐
│              API Gateway / Routing                       │
│  FastAPI Application with CORS Middleware              │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│           Business Logic Services                       │
│  ├─ Patient Service (患者管理)                         │
│  ├─ EMR Service (电子病历)                            │
│  ├─ Analysis Service (诊断分析)                       │
│  ├─ Report Service (报告管理)                         │
│  └─ Device Service (设备数据)                         │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
   ┌────────┐ ┌─────────┐ ┌──────────┐
   │ MySQL  │ │File Sys │ │Device Fs │
   │Database│ │(Reports)│ │ (Images) │
   └────────┘ └─────────┘ └──────────┘
```

---

## 二、前端架构 (Frontend Architecture)

### 2.1 项目结构

```
frontend/
├── public/                 # 静态资源
├── src/
│   ├── app/               # Next.js App Router
│   │   ├── layout.tsx     # 根布局
│   │   ├── page.tsx       # 首页
│   │   ├── patients/      # 患者模块
│   │   │   └── page.tsx   # 患者列表页
│   │   ├── emr/           # EMR模块
│   │   │   └── page.tsx   # EMR管理页
│   │   ├── treatment/     # 治疗方案模块
│   │   │   └── page.tsx   # 治疗方案页
│   │   └── upload/        # 上传模块
│   │       └── page.tsx   # 数据上传页
│   ├── components/        # 可复用组件
│   │   ├── ReportModal.tsx
│   │   ├── PatientForm.tsx
│   │   └── ...
│   ├── hooks/            # 自定义 Hooks
│   │   ├── useLocalStorage.ts
│   │   └── useFetch.ts
│   ├── types/            # TypeScript 类型定义
│   │   ├── patient.ts
│   │   ├── emr.ts
│   │   └── ...
│   └── utils/            # 工具函数
│       ├── api.ts        # API 调用
│       ├── format.ts     # 格式化函数
│       └── ...
├── package.json
└── tsconfig.json
```

### 2.2 核心页面设计

#### 患者管理页面 (patients/page.tsx)

**数据状态**:
```typescript
// UI状态
- showRegisterForm: boolean        // 注册表单显示
- showDetailModal: boolean         // 详情模态框显示
- showReportModal: boolean         // 报告模态框显示
- showReportPreview: boolean       // 报告预览显示

// 数据状态
- patients: Patient[]              // 患者列表
- selectedPatient: Patient | null  // 当前选中患者
- emrs: EmrRecord[]               // EMR列表
- reportFiles: ReportFile[]       // 报告文件列表

// 分页状态
- page: number                     // 当前页号
- hasMore: boolean                 // 是否有更多数据
- loading: boolean                 // 是否加载中

// 表单状态
- formData: NewPatient            // 新患者表单数据
- searchQuery: string             // 搜索查询 (持久化)

// 流程状态 (localStorage)
- currentPatientId: string        // 当前患者ID
- currentPatient: Patient         // 当前患者信息
```

**核心功能**:
1. **患者列表展示** (fetchPatients)
   - 支持分页加载
   - 支持关键词搜索
   - 支持无限滚动

2. **患者注册** (handleRegisterPatient)
   - 表单验证
   - 数据提交
   - 自动跳转到上传页

3. **报告管理** (handleOpenReportHistory)
   - 获取患者报告列表
   - 支持预览/打印/下载

#### EMR管理页面 (emr/page.tsx)

**数据状态**:
```typescript
// UI状态
- selectedPatient: Patient | null
- selectedRecord: Record | null
- showGenerateModal: boolean

// 数据状态
- emrList: EmrRecord[]
- recordList: Record[]
- emrDetails: EmrDetail | null

// 表单状态
- diagnosis: string              // 诊断分析
- doctorOpinion: string         // 医生意见

// 流程状态 (localStorage)
- recordId: string              // 当前记录ID
- emrId: string                 // 当前EMR ID
- patientId: string             // 当前患者ID
- last_emr_context: object      // 保存给treatment页面
```

**核心功能**:
1. **EMR查询** (fetchPatientEmrs)
   - 获取患者EMR列表
   - 支持按日期排序

2. **EMR生成** (handleGenerateEmr)
   - 基于设备数据生成
   - 自动分析
   - 保存结果

3. **诊断输入** (handleInputChange)
   - 实时保存到localStorage
   - 支持长文本编辑
   - 返回时恢复数据

#### 治疗方案页面 (treatment/page.tsx)

**数据状态**:
```typescript
// UI状态
- selectedPatientId: string | null
- showRecommendation: boolean

// 数据状态
- emrRecords: EmrRecord[]
- treatmentPlan: string

// 流程状态 (localStorage)
- last_emr_context: object      // 来自EMR页面
- currentPatient: Patient       // 当前患者
```

**核心功能**:
1. **患者自动选择** (useEffect)
   - 从localStorage读取上次诊断的患者
   - 自动加载EMR记录
   - 支持手动切换患者

2. **方案生成** (handleGeneratePlan)
   - 基于诊断生成方案
   - 支持编辑和调整
   - 保存到localStorage

#### 上传页面 (upload/page.tsx)

**数据状态**:
```typescript
// 表单状态 (全部持久化到localStorage)
- deviceId: string
- deviceModel: string
- captureTime: string
- patientName: string
- gender: string
- age: string
- bodyPart: string

// UI状态
- uploading: boolean
- uploadProgress: number
- uploadError: string | null
```

**核心功能**:
1. **表单持久化** (useEffect)
   - 每个字段变更时保存
   - 页面加载时恢复
   - 返回时保留输入

2. **文件上传** (handleUpload)
   - 支持拖拽上传
   - 显示上传进度
   - 自动触发分析

### 2.3 状态管理策略

**分类**:
```
┌─────────────────────────────────────────┐
│        Frontend State Management         │
├─────────────────────────────────────────┤
│ 1. UI State (内存)                      │
│    └─ 模态框/表单显示状态                 │
│                                         │
│ 2. Data State (内存 + API同步)           │
│    └─ 患者/EMR/报告列表                 │
│                                         │
│ 3. Form State (内存 + localStorage)      │
│    └─ 正在编辑的表单数据                 │
│                                         │
│ 4. Flow State (localStorage)            │
│    └─ 跨页面的流程上下文数据              │
└─────────────────────────────────────────┘
```

**持久化键值**:
```typescript
PATIENTS_STATE_KEY = "patient_flow_state_patients"
UPLOAD_STATE_KEY = "patient_flow_state_upload"
EMR_STATE_KEY = "patient_flow_state_emr"
TREATMENT_STATE_KEY = "patient_flow_state_treatment"
LAST_EMR_CONTEXT_KEY = "last_emr_context"
```

**清空规则**:
- 点击"新增患者"时: 清空所有流程状态
- 点击"新上传"时: 清空上传表单状态
- 导航到其他患者时: 更新流程上下文

### 2.4 组件设计原则

**组件分类**:
```
1. Page Components (页面组件)
   - 位于 app/ 目录
   - 处理整个页面的逻辑
   - 与API和localStorage交互

2. Feature Components (功能组件)
   - 位于 components/ 目录
   - 处理特定功能模块
   - 接收props和回调函数

3. Reusable Components (复用组件)
   - 通用UI组件 (按钮、输入框等)
   - 不包含业务逻辑
   - 高度参数化
```

---

## 三、后端架构 (Backend Architecture)

### 3.1 项目结构

```
ingestion/
├── app/
│   ├── main.py                 # 应用入口 + 路由定义
│   ├── config.py               # 配置管理
│   ├── models.py               # Pydantic 数据模型
│   │
│   ├── data_platform.py        # 数据访问层 (DAL)
│   │   ├─ init_db()
│   │   ├─ list_patients()      # 分页查询患者
│   │   ├─ upsert_patient()
│   │   ├─ list_records()
│   │   ├─ list_emrs()
│   │   └─ ...
│   │
│   ├── analysis.py             # 业务逻辑层 (BLL)
│   │   └─ analyze_record()
│   │
│   ├── emr.py                  # EMR 处理
│   │   ├─ generate_emr()
│   │   ├─ get_emr()
│   │   ├─ list_emrs()
│   │   ├─ update_emr()
│   │   ├─ archive_emr()
│   │   └─ ...
│   │
│   ├── device_connector.py     # 设备数据读取
│   │   ├─ ingest_capture_dir()
│   │   ├─ move_capture_dir()
│   │   └─ ...
│   │
│   ├── dispatch.py             # 数据分发
│   │   └─ dispatch_record()
│   │
│   ├── qc.py                   # 质量检查
│   │   └─ run_qc()
│   │
│   ├── storage.py              # 文件存储
│   │   └─ save_payload()
│   │
│   └── database.py             # 数据库连接
│       ├─ _connect()
│       └─ _cursor()
│
├── tests/                      # 单元测试
│   ├─ test_data_platform.py
│   ├─ test_emr.py
│   └─ ...
│
├── requirements.txt            # Python依赖
├── Dockerfile                  # 容器镜像
└── README.md
```

### 3.2 核心服务说明

#### 数据访问层 (data_platform.py)

**职责**: 数据库CRUD操作

**关键函数**:
```python
# 患者管理
list_patients(limit=100, offset=0)        # 分页查询患者
upsert_patient(...)                       # 创建/更新患者

# 记录查询
list_records(patient_id, limit=50)        # 查询患者记录

# EMR管理
list_emrs(patient_id, limit=50, ...)      # 查询EMR列表
get_emr(emr_id)                           # 获取单个EMR
update_emr(emr_id, ...)                   # 更新EMR
archive_emr(emr_id)                       # 归档EMR
```

**连接管理**:
```python
def _connect():
    # 创建MySQL连接
    # 返回连接对象供with语句使用
    
with _connect() as conn:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
```

#### 业务逻辑层 (emr.py, analysis.py)

**职责**: 核心业务逻辑

**EMR服务**:
```python
generate_emr(record_id, patient_id)       # 从记录生成EMR
get_emr(emr_id)                           # 获取EMR详情
list_emrs(patient_id)                     # 列出患者EMR
update_emr(emr_id, updates)               # 更新EMR
archive_emr(emr_id)                       # 归档EMR
```

**分析服务**:
```python
analyze_record(record_id)                 # 分析记录数据
  ├─ 读取原始数据
  ├─ 图像处理/分析
  ├─ 提取特征
  ├─ 生成诊断建议
  └─ 保存分析结果
```

#### 文件存储层 (storage.py)

**职责**: 文件和二进制数据管理

**关键函数**:
```python
save_payload(filename, file_bytes, metadata)
  # 保存上传的文件
  # 返回: {file_id, file_path, saved_at}

get_payload(file_id)
  # 读取已保存的文件
```

### 3.3 API设计

**路由和端点**:

```
患者管理:
  GET    /patients                    # 获取患者列表 (支持分页)
  POST   /patients                    # 创建患者
  GET    /patients/{id}               # 获取患者详情
  PUT    /patients/{id}               # 更新患者信息

设备数据:
  POST   /ingest                      # 上传文件
  POST   /device/ingest               # 从设备读取数据
  POST   /analyze                     # 分析数据

EMR管理:
  GET    /emr                         # 获取EMR列表
  GET    /emr/{id}                    # 获取EMR详情
  POST   /emr/generate                # 生成新EMR
  PUT    /emr/{id}                    # 更新EMR
  POST   /emr/{id}/archive            # 归档EMR

报告管理:
  GET    /reports                     # 获取报告列表
  GET    /reports/{date}/{filename}   # 下载报告
  GET    /reports/preview             # 预览报告 (浏览器内打开)

数据分析:
  POST   /dispatch                    # 分发数据
  GET    /platform/records            # 查询记录
  GET    /platform/emrs               # 查询平台EMR
```

**API参数规范**:

```
分页参数:
  - page: int (默认1)
  - limit: int (默认20)

查询参数:
  - patient_id: str
  - date_from: str (YYYY-MM-DD)
  - date_to: str (YYYY-MM-DD)

响应格式:
  {
    "data": [...],
    "total": 100,
    "page": 1,
    "limit": 20
  }

错误响应:
  {
    "detail": "error_message",
    "status_code": 400
  }
```

### 3.4 数据库设计

#### 患者表 (patients)

```sql
CREATE TABLE patients (
  patient_id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  gender VARCHAR(10),
  age INT,
  birth_date DATE,
  id_card VARCHAR(50),
  phone VARCHAR(20),
  address TEXT,
  emergency_contact VARCHAR(100),
  emergency_phone VARCHAR(20),
  allergies TEXT,
  medical_history TEXT,
  department VARCHAR(50),
  chief_complaint TEXT,
  payload_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  INDEX idx_name (name),
  INDEX idx_updated_at (updated_at)
);
```

#### 记录表 (records)

```sql
CREATE TABLE records (
  record_id VARCHAR(36) PRIMARY KEY,
  patient_id VARCHAR(36) NOT NULL,
  device_id VARCHAR(100),
  device_model VARCHAR(50),
  body_part VARCHAR(100),
  capture_time TIMESTAMP,
  file_path VARCHAR(255),
  file_size INT,
  payload_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
  INDEX idx_patient_id (patient_id),
  INDEX idx_created_at (created_at)
);
```

#### EMR表 (emrs)

```sql
CREATE TABLE emrs (
  emr_id VARCHAR(36) PRIMARY KEY,
  record_id VARCHAR(36) NOT NULL,
  patient_id VARCHAR(36) NOT NULL,
  diagnosis TEXT,
  analysis_result JSON,
  archived BOOLEAN DEFAULT FALSE,
  payload_json JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
  FOREIGN KEY (record_id) REFERENCES records(record_id),
  INDEX idx_patient_id (patient_id),
  INDEX idx_archived (archived)
);
```

### 3.5 错误处理

**HTTPException 使用**:
```python
from fastapi import HTTPException

# 400 Bad Request
raise HTTPException(status_code=400, detail="invalid_input")

# 404 Not Found
raise HTTPException(status_code=404, detail="patient_not_found")

# 500 Internal Server Error
raise HTTPException(status_code=500, detail="processing_failed")
```

**错误响应格式**:
```json
{
  "detail": "error_message",
  "status_code": 400
}
```

---

## 四、通信协议

### 4.1 HTTP方法规范

| 方法 | 操作 | 示例 |
|-----|-----|------|
| GET | 查询 | GET /patients 获取列表 |
| POST | 创建 | POST /patients 创建患者 |
| PUT | 更新 | PUT /patients/{id} 更新患者 |
| DELETE | 删除 | DELETE /patients/{id} 删除患者 |

### 4.2 跨域配置 (CORS)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应改为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4.3 请求/响应示例

**创建患者**:
```
POST /patients
Content-Type: application/json

{
  "name": "张三",
  "gender": "男",
  "birth_date": "1990-01-01",
  "phone": "13800138000",
  ...
}

Response: 201 Created
{
  "patient_id": "uuid-xxxx",
  "name": "张三",
  ...
}
```

**获取患者列表 (分页)**:
```
GET /patients?page=1&limit=20

Response: 200 OK
[
  {
    "patient_id": "uuid-1",
    "name": "张三",
    "gender": "男",
    "age": 34,
    "updated_at": "2026-02-12T10:00:00"
  },
  ...
]
```

---

## 五、数据流向

### 5.1 患者注册流程

```
用户在前端填写患者信息
        ↓
点击"注册患者"
        ↓
POST /patients (JSON数据)
        ↓
后端验证数据
        ↓
data_platform.upsert_patient()
        ↓
MySQL 存储患者数据
        ↓
返回 patient_id
        ↓
前端重定向到 /upload?name=...&gender=...
```

### 5.2 数据上传流程

```
用户选择设备数据文件
        ↓
前端显示上传进度
        ↓
POST /ingest (multipart/form-data)
        ↓
后端验证文件
        ↓
storage.save_payload() 保存文件
        ↓
POST /analyze 触发分析
        ↓
analysis.analyze_record() 处理
        ↓
生成分析结果
        ↓
返回结果给前端
```

### 5.3 EMR生成流程

```
医生选择患者和记录
        ↓
点击"生成EMR"
        ↓
POST /emr/generate {record_id, patient_id}
        ↓
后端emr.generate_emr()
  ├─ 读取记录数据
  ├─ 调用analysis.analyze_record()
  ├─ 生成诊断建议
  └─ 保存到数据库
        ↓
返回 emr_id 和生成结果
        ↓
前端显示结果供医生编辑
```

---

## 六、性能优化

### 6.1 查询优化

**数据库索引**:
```sql
-- 患者查询优化
CREATE INDEX idx_patients_name ON patients(name);
CREATE INDEX idx_patients_updated_at ON patients(updated_at DESC);

-- 记录查询优化
CREATE INDEX idx_records_patient_id ON records(patient_id);

-- EMR查询优化
CREATE INDEX idx_emrs_patient_id ON emrs(patient_id);
CREATE INDEX idx_emrs_archived ON emrs(archived);
```

**分页查询**:
```python
# 获取第1页，每页20条
SELECT * FROM patients
ORDER BY updated_at DESC
LIMIT 20 OFFSET 0;
```

### 6.2 前端优化

**代码分割**:
- 使用Next.js动态导入减小bundle
- 每个页面单独的JavaScript文件

**缓存策略**:
- API响应缓存在localStorage (Flow State)
- 图片懒加载
- 组件记忆化 (React.memo)

### 6.3 API优化

**响应压缩**:
```python
from fastapi.middleware.gzip import GZIPMiddleware
app.add_middleware(GZIPMiddleware, minimum_size=1000)
```

**超时设置**:
- API响应超时: 30秒
- 数据库查询超时: 10秒

---

## 七、安全考虑

### 7.1 CORS配置

生产环境:
```python
allow_origins=[
    "https://yourdomain.com",
    "https://www.yourdomain.com"
]
```

### 7.2 数据验证

```python
from pydantic import BaseModel, Field

class NewPatient(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    gender: str
    birth_date: str
    phone: str = Field(..., regex=r'^\d{11}$')
```

### 7.3 错误信息

生产环境不要暴露详细的技术信息:
```python
# ❌ 不要这样做
raise HTTPException(detail=f"Database error: {str(e)}")

# ✅ 应该这样做
logger.error(f"Database error: {str(e)}")
raise HTTPException(status_code=500, detail="server_error")
```

---

## 总结

本系统采用 **分层架构**:
- **展示层**: Next.js React 组件
- **业务逻辑层**: FastAPI 服务
- **数据访问层**: Python数据库操作
- **数据层**: MySQL + 文件系统

通过清晰的分层和职责划分，保证了代码的可维护性和可扩展性。
