# API 规范文档

## 一、API总览

基础URL: `http://localhost:8000`

所有API均返回JSON格式数据，使用标准HTTP状态码。

---

## 二、患者管理 API

### 2.1 获取患者列表

**请求**:
```
GET /patients?page=1&limit=20
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| page | integer | 否 | 页码，默认1 |
| limit | integer | 否 | 每页条数，默认20 |

**响应** (200 OK):
```json
[
  {
    "patient_id": "uuid-123456",
    "name": "张三",
    "gender": "男",
    "age": 34,
    "phone": "13800138000",
    "address": "北京市朝阳区",
    "updated_at": "2026-02-12T10:00:00"
  },
  ...
]
```

**错误响应**:
```json
{
  "detail": "invalid_page_number"
}
```

---

### 2.2 创建患者

**请求**:
```
POST /patients
Content-Type: application/json
```

**请求体**:
```json
{
  "name": "李四",
  "gender": "女",
  "birth_date": "1992-05-15",
  "id_card": "110101199205151234",
  "phone": "13900139000",
  "address": "北京市海淀区",
  "emergency_contact": "王五",
  "emergency_phone": "13700137000",
  "allergies": "青霉素",
  "medical_history": "高血压病史5年",
  "department": "中医科",
  "chief_complaint": "头晕头痛"
}
```

**必需字段**:
- name: 患者姓名
- gender: 性别 (男/女)
- birth_date: 出生日期 (YYYY-MM-DD)

**可选字段**:
- 其他所有字段

**响应** (201 Created):
```json
{
  "patient_id": "uuid-789012",
  "name": "李四",
  "gender": "女",
  "birth_date": "1992-05-15",
  "phone": "13900139000",
  "message": "patient_registered_successfully"
}
```

**错误响应**:
```json
{
  "detail": "invalid_patient_data"
}
```

---

### 2.3 获取患者详情

**请求**:
```
GET /patients/{patient_id}
```

**路径参数**:
| 参数 | 类型 | 说明 |
|-----|------|------|
| patient_id | string | 患者ID (UUID) |

**响应** (200 OK):
```json
{
  "patient_id": "uuid-123456",
  "name": "张三",
  "gender": "男",
  "age": 34,
  "birth_date": "1990-01-01",
  "phone": "13800138000",
  "address": "北京市朝阳区",
  "emergency_contact": "张四",
  "emergency_phone": "13800138001",
  "allergies": "头孢菌素",
  "medical_history": "糖尿病病史3年",
  "department": "中医科",
  "chief_complaint": "腰痛",
  "created_at": "2026-02-10T08:00:00",
  "updated_at": "2026-02-12T10:00:00"
}
```

**错误响应**:
```json
{
  "detail": "patient_not_found"
}
```

---

## 三、设备数据 API

### 3.1 上传设备数据

**请求**:
```
POST /ingest
Content-Type: multipart/form-data
```

**表单参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| file | file | 是 | 设备数据文件 |
| metadata | string | 是 | JSON格式的元数据 |

**元数据示例** (JSON字符串):
```json
{
  "device_id": "device-001",
  "device_model": "Scanner-X100",
  "patient_name": "张三",
  "patient_id": "uuid-123456",
  "capture_time": "2026-02-12T09:30:00",
  "body_part": "胸部",
  "operator": "李医生"
}
```

**响应** (200 OK):
```json
{
  "file_id": "file-uuid-001",
  "file_path": "/data/uploads/file-uuid-001",
  "file_size": 5242880,
  "saved_at": "2026-02-12T10:00:00",
  "qc_issues": [
    {
      "code": "QC001",
      "severity": "warning",
      "message": "图像质量低"
    }
  ]
}
```

**支持的文件类型**:
- `.dicom`, `.dcm` - DICOM医学影像
- `.jpg`, `.jpeg`, `.png` - 图像文件
- `.zip` - 压缩包

**最大文件大小**: 500 MB

**错误响应**:
```json
{
  "detail": "unsupported_file_type"
}
```

---

### 3.2 分析设备数据

**请求**:
```
POST /analyze
Content-Type: application/json
```

**请求体**:
```json
{
  "record_id": "record-uuid-001"
}
```

**响应** (200 OK):
```json
{
  "record_id": "record-uuid-001",
  "analysis_status": "completed",
  "analysis_result": {
    "key_findings": [
      "发现肺部异常阴影",
      "右下肺少量积液"
    ],
    "recommendations": [
      "建议进一步CT检查",
      "建议拍胸部正侧位片"
    ],
    "confidence_score": 0.92,
    "analysis_time": "2026-02-12T10:05:00"
  },
  "emr_id": "emr-uuid-001"
}
```

**错误响应**:
```json
{
  "detail": "record_not_found"
}
```

---

## 四、电子病历 (EMR) API

### 4.1 获取EMR列表

**请求**:
```
GET /emr?patient_id=uuid-123456&limit=50&include_archived=false
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| patient_id | string | 否 | 患者ID过滤 |
| limit | integer | 否 | 返回条数，默认50 |
| include_archived | boolean | 否 | 是否包含已归档，默认false |

**响应** (200 OK):
```json
[
  {
    "emr_id": "emr-uuid-001",
    "record_id": "record-uuid-001",
    "patient_id": "uuid-123456",
    "patient": {
      "name": "张三",
      "gender": "男",
      "age": 34
    },
    "diagnosis": "肺部感染",
    "analysis_result": {
      "key_findings": [...],
      "confidence_score": 0.92
    },
    "archived": false,
    "created_at": "2026-02-12T10:05:00",
    "updated_at": "2026-02-12T10:05:00"
  },
  ...
]
```

---

### 4.2 获取EMR详情

**请求**:
```
GET /emr/{emr_id}
```

**路径参数**:
| 参数 | 类型 | 说明 |
|-----|------|------|
| emr_id | string | EMR ID (UUID) |

**响应** (200 OK):
```json
{
  "emr_id": "emr-uuid-001",
  "record_id": "record-uuid-001",
  "patient_id": "uuid-123456",
  "diagnosis": "肺部感染，建议抗感染治疗",
  "analysis_result": {
    "key_findings": [
      "左肺中上叶见浸润影",
      "纵隔淋巴结肿大"
    ],
    "severity": "moderate"
  },
  "archived": false,
  "created_at": "2026-02-12T10:05:00"
}
```

---

### 4.3 生成新EMR

**请求**:
```
POST /emr/generate
Content-Type: application/json
```

**请求体**:
```json
{
  "record_id": "record-uuid-001",
  "patient_id": "uuid-123456"
}
```

**响应** (201 Created):
```json
{
  "emr_id": "emr-uuid-new",
  "record_id": "record-uuid-001",
  "patient_id": "uuid-123456",
  "diagnosis": "自动生成的诊断",
  "analysis_result": {...},
  "created_at": "2026-02-12T10:10:00"
}
```

---

### 4.4 更新EMR

**请求**:
```
PUT /emr/{emr_id}
Content-Type: application/json
```

**请求体**:
```json
{
  "diagnosis": "更新后的诊断结果"
}
```

**响应** (200 OK):
```json
{
  "emr_id": "emr-uuid-001",
  "diagnosis": "更新后的诊断结果",
  "updated_at": "2026-02-12T10:15:00"
}
```

---

### 4.5 归档EMR

**请求**:
```
POST /emr/{emr_id}/archive
```

**响应** (200 OK):
```json
{
  "emr_id": "emr-uuid-001",
  "archived": true,
  "archived_at": "2026-02-12T10:20:00"
}
```

---

## 五、报告管理 API

### 5.1 获取报告列表 (支持日期过滤)

**请求**:
```
GET /reports?date=2026-02-11
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| date | string | 否 | 日期过滤 (YYYY-MM-DD)，仅返回该日期的报告 |

**响应** (200 OK):
```json
[
  {
    "date": "2026-02-11",
    "name": "张三_20260211_170700.docx",
    "size_bytes": 204800,
    "url": "/reports/2026-02-11/张三_20260211_170700.docx",
    "updated_at": 1707639900
  },
  ...
]
```

**说明**:
- 如果不提供 `date` 参数，返回所有报告（按日期倒序）
- 如果提供 `date` 参数，只返回该日期的报告
- 前端可基于此API返回的日期信息实现日期范围过滤

---

### 5.2 下载报告

**请求**:
```
GET /reports/{date}/{filename}
```

**路径参数**:
| 参数 | 类型 | 说明 |
|-----|------|------|
| date | string | 报告日期 (YYYY-MM-DD) |
| filename | string | 文件名 (URL编码) |

**示例**:
```
GET /reports/2026-02-11/%E5%BC%A0%E7%9B%8A%E9%93%AD_20260211_170700.docx
```

**响应** (200 OK):
- Content-Type: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- Content-Disposition: `attachment; filename="..."`
- 文件二进制内容

**错误响应** (404 Not Found):
```json
{
  "detail": "file_not_found"
}
```

---

### 5.3 预览报告 (浏览器内打开)

**请求**:
```
GET /reports/preview?date=2026-02-11&filename=张三_20260211_170700.docx
```

**查询参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| date | string | 是 | 报告日期 (URL编码) |
| filename | string | 是 | 文件名 (URL编码) |

**响应** (200 OK):
- Content-Type: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- Content-Disposition: `inline` (浏览器内打开，不下载)
- 文件二进制内容

---

## 六、数据查询 API

### 6.1 查询记录列表

**请求**:
```
GET /platform/records?patient_id=uuid-123456&limit=50
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| patient_id | string | 否 | 患者ID过滤 |
| limit | integer | 否 | 返回条数，默认50 |

**响应** (200 OK):
```json
[
  {
    "record_id": "record-uuid-001",
    "patient_id": "uuid-123456",
    "device_id": "device-001",
    "device_model": "Scanner-X100",
    "body_part": "胸部",
    "capture_time": "2026-02-12T09:30:00",
    "file_path": "/data/records/...",
    "created_at": "2026-02-12T10:00:00"
  },
  ...
]
```

---

### 6.2 查询平台EMR

**请求**:
```
GET /platform/emrs?patient_id=uuid-123456&limit=50&include_archived=false
```

**参数**:
| 参数 | 类型 | 必需 | 说明 |
|-----|------|-----|------|
| patient_id | string | 否 | 患者ID过滤 |
| limit | integer | 否 | 返回条数，默认50 |
| include_archived | boolean | 否 | 是否包含已归档 |

**响应** (200 OK):
```json
[
  {
    "emr_id": "emr-uuid-001",
    "patient_id": "uuid-123456",
    "diagnosis": "肺部感染",
    "archived": false,
    "created_at": "2026-02-12T10:05:00"
  },
  ...
]
```

---

## 七、数据分发 API

### 7.1 分发记录

**请求**:
```
POST /dispatch
Content-Type: application/json
```

**请求体**:
```json
{
  "record_id": "record-uuid-001"
}
```

**响应** (200 OK):
```json
{
  "record_id": "record-uuid-001",
  "dispatch_status": "success",
  "dispatch_targets": [
    {
      "target": "emr_system",
      "status": "success",
      "timestamp": "2026-02-12T10:10:00"
    }
  ]
}
```

---

## 八、HTTP状态码

| 状态码 | 含义 | 示例 |
|-------|------|------|
| 200 | 成功 | GET请求成功 |
| 201 | 创建成功 | POST创建资源 |
| 400 | 请求错误 | 参数格式错误 |
| 401 | 未认证 | 无认证令牌 |
| 403 | 禁止访问 | 无权限操作 |
| 404 | 未找到 | 资源不存在 |
| 500 | 服务器错误 | 未捕获的异常 |

---

## 九、错误响应格式

**统一错误响应**:
```json
{
  "detail": "error_code_or_message"
}
```

**常见错误代码**:
| 错误代码 | HTTP状态 | 说明 |
|--------|--------|------|
| invalid_input | 400 | 输入数据无效 |
| patient_not_found | 404 | 患者不存在 |
| emr_not_found | 404 | EMR不存在 |
| file_not_found | 404 | 文件不存在 |
| unsupported_file_type | 400 | 不支持的文件类型 |
| file_too_large | 400 | 文件过大 |
| database_error | 500 | 数据库错误 |

---

## 十、数据类型定义

### Patient (患者)
```typescript
{
  patient_id: string (UUID)
  name: string
  gender: string ("男" | "女")
  age?: number
  birth_date?: string (YYYY-MM-DD)
  phone?: string
  address?: string
  emergency_contact?: string
  emergency_phone?: string
  allergies?: string
  medical_history?: string
  department?: string
  chief_complaint?: string
  created_at: string (ISO 8601)
  updated_at: string (ISO 8601)
}
```

### EMR (电子病历)
```typescript
{
  emr_id: string (UUID)
  record_id: string (UUID)
  patient_id: string (UUID)
  diagnosis: string
  analysis_result?: object
  archived: boolean
  created_at: string (ISO 8601)
  updated_at: string (ISO 8601)
}
```

### ReportFile (报告文件)
```typescript
{
  date: string (YYYY-MM-DD)
  name: string
  size_bytes: number
  url: string
  updated_at: number (Unix timestamp)
}
```

---

## 十一、API使用示例

### 完整患者工作流

```javascript
// 1. 创建患者
const patient = await fetch('http://localhost:8000/patients', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: '张三',
    gender: '男',
    birth_date: '1990-01-01'
  })
}).then(r => r.json());

// 2. 上传设备数据
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('metadata', JSON.stringify({
  patient_id: patient.patient_id,
  device_model: 'Scanner-X100',
  body_part: '胸部'
}));

const upload = await fetch('http://localhost:8000/ingest', {
  method: 'POST',
  body: formData
}).then(r => r.json());

// 3. 分析数据
const analysis = await fetch('http://localhost:8000/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ record_id: upload.record_id })
}).then(r => r.json());

// 4. 获取报告
const reports = await fetch('http://localhost:8000/reports').then(r => r.json());
```

---

## 最后更新

- **版本**: 1.0
- **更新时间**: 2026-02-12
- **维护者**: 医疗系统开发团队
