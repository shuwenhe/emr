# PDF 报告预览功能 - 实现指南

## 功能概述

此实现提供了一个完整的端到端 PDF 报告在线预览功能，包括：

- ✅ **后端 API** - 已支持 PDF 文件的内联服务（inline serving）
- ✅ **前端 PDF 查看器** - React 组件，支持分页浏览、跳转、打印
- ✅ **历史报告页面** - 完整的报告列表、搜索、过滤功能
- ✅ **导航集成** - 在网站导航中添加"历史报告"链接

## 文件结构

```
emr/
├── web/
│   ├── package.json                          (已更新：添加 react-pdf, pdfjs-dist)
│   └── src/app/
│       ├── layout.tsx                        (已更新：添加报告页面导航)
│       ├── components/
│       │   └── PDFViewer.tsx                 (新增：PDF 查看器组件)
│       └── reports/
│           └── page.tsx                      (新增：历史报告页面)
└── route/
    └── reports.py                            (已支持 inline 参数的 GET /reports/{date}/{filename})
```

## 安装步骤

### 1. 安装前端依赖

```bash
cd /home/shuwen/emr/web
npm install
# 或
npm ci
```

**新安装的依赖：**
- `react-pdf@^8.0.0` - PDF 渲染库
- `pdfjs-dist@^4.0.0` - PDF.js 核心库

### 2. 启动前端开发服务器

```bash
npm run dev
# 在 http://localhost:3000 访问
```

### 3. 启动后端服务

```bash
cd /home/shuwen/emr
# 确保 reportlab 已安装（之前已完成）
python -m uvicorn route.main:app --reload --host 0.0.0.0 --port 8000
```

## 使用指南

### 访问历史报告页面

1. 启动前端应用后，点击导航栏中的 **"历史报告"** 链接
2. 进入 `/reports` 页面，显示所有可用的历史报告文件

### 查看 PDF 报告

#### 方式一：在线预览
1. 在报告列表中找到 `.pdf` 文件
2. 点击 **"查看"** 按钮
3. 弹出 PDF 查看器模态框

#### 方式二：下载
点击 **"下载"** 按钮直接下载文件到本地

#### 方式三：打印
点击 **"打印"** 按钮用浏览器打印功能打印 PDF

### 搜索和过滤

- **按名称搜索** - 在搜索框输入报告名称
- **按日期筛选** - 从下拉菜单选择特定日期
- 支持实时过滤

## API 端点

### 获取报告列表
```
GET /reports
GET /reports?date=20260311
```

**响应示例：**
```json
[
  {
    "date": "20260311",
    "name": "庄晓浩_20260311_102700_EMR-93a1281d-2417-4cc5-a70f-4577e14b5b79.pdf",
    "size_bytes": 409600,
    "url": "/reports/20260311/庄晓浩_20260311_102700_EMR-93a1281d-2417-4cc5-a70f-4577e14b5b79.pdf",
    "updated_at": 1710163620
  }
]
```

### 获取单个报告

#### 下载（附件形式）
```
GET /reports/{date}/{filename}
```

#### 在线预览（内联显示）
```
GET /reports/{date}/{filename}?inline=true
```

**示例：**
```
GET /reports/20260311/report.pdf?inline=true
```

## 前端组件

### PDFViewer 组件

文件：`web/src/app/components/PDFViewer.tsx`

```typescript
interface PDFViewerProps {
  pdfUrl: string;      // PDF 文件的 URL
  title: string;       // 显示的标题
  onClose: () => void; // 关闭回调函数
}
```

**使用示例：**
```typescript
import PDFViewer from "@/app/components/PDFViewer";

export default function MyComponent() {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  return (
    <>
      {/* 其他内容 */}
      {pdfUrl && (
        <PDFViewer
          pdfUrl={pdfUrl}
          title="我的报告.pdf"
          onClose={() => setPdfUrl(null)}
        />
      )}
    </>
  );
}
```

**功能：**
- ✅ 显示 PDF 文件
- ✅ 分页浏览（上一页/下一页）
- ✅ 跳转到指定页码
- ✅ 显示总页数
- ✅ 加载状态提示
- ✅ 错误处理
- ✅ 响应式设计

### 历史报告页面

文件：`web/src/app/reports/page.tsx`

**功能：**
- 显示所有报告文件列表
- 按名称搜索
- 按日期过滤
- 在线预览 PDF
- 下载文件
- 打印 PDF
- 显示统计信息（总数、大小、日期数量）

## 系统要求

### 后端
- Python 3.12
- FastAPI
- reportlab（已安装）
- PDF 文件存储在 `REPORTS_DIR`

### 前端
- Node.js 18+
- npm/yarn
- 现代浏览器（Chrome、Firefox、Safari、Edge）

## 配置

### 后端配置

确保 `core/config.py` 中定义了 `REPORTS_DIR`：

```python
REPORTS_DIR = Path(settings.get("REPORTS_DIR", "./reports"))
```

### 前端 API 基础 URL

在 `web/src/app/reports/page.tsx` 中修改：

```typescript
const API_BASE = "http://localhost:8000";  // 根据需要调整
```

## 故障排查

### PDF 无法加载
1. 检查 API 服务是否运行（`http://localhost:8000/reports`）
2. 验证报告文件是否存在于 `REPORTS_DIR`
3. 检查浏览器控制台错误信息

### 依赖安装失败
```bash
# 清除 node_modules 和缓存
rm -rf node_modules package-lock.json
npm install
```

### 跨域问题
如果前端和后端在不同的域/端口上，配置后端 CORS：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 改进建议

1. **DOCX 支持** - 添加 DOCX 文件的在线预览
2. **缓存** - 实现 PDF 缓存以提高性能
3. **权限控制** - 添加基于用户权限的文件访问控制
4. **批量操作** - 支持下载多个报告的压缩包
5. **标注** - 添加 PDF 标注功能
6. **版本控制** - 追踪报告版本历史

## 测试检查清单

- [ ] 安装前端依赖成功
- [ ] 后端 API 服务运行正常
- [ ] 能访问 `/reports` 页面
- [ ] 报告列表正确显示
- [ ] 搜索功能正常工作
- [ ] 日期过滤功能正常工作
- [ ] PDF 预览在线打开成功
- [ ] 分页导航功能正常
- [ ] 下载功能正常
- [ ] 打印功能正常
- [ ] 响应式设计在移动设备上正常显示

## 支持的文件格式

- ✅ **PDF** (.pdf) - 完全支持在线预览
- 📋 **DOCX** (.docx) - 下载和查看支持（在线预览开发中）

## 性能优化

1. PDF.js 使用 CDN 版本的 worker：
   ```javascript
   pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;
   ```

2. 报告列表支持缓存（3600 秒 TTL）

3. PDF 文件流式下载，避免大文件问题

## 许可证

与主项目相同
