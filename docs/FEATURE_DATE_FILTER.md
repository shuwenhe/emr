# 功能实现：日期范围搜索报告

## 功能需求 (R006)

**用户故事**:
医生需要搜索特定日期范围内的患者报告，以便进行对比诊断和历史追踪。

**验收标准**:
1. ✅ 支持日期范围选择 (起始日期 + 结束日期)
2. ✅ 搜索患者对应的报告并按日期过滤
3. ⏳ 支持批量操作 (后续实现)

**优先级**: P2 (High)

---

## 实现方案

### 前端实现 (Frontend)

**文件**: `frontend/src/app/patients/page.tsx`

**新增状态**:
```typescript
// 报告日期范围过滤状态
const [reportDateFrom, setReportDateFrom] = useState("");
const [reportDateTo, setReportDateTo] = useState("");
```

**核心函数**:

1. **filterReportsForPatient()** - 增强的过滤函数
```typescript
function filterReportsForPatient(files: ReportFile[], patient: Patient | null) {
  // 按患者名字或ID过滤
  const matchPatient = (name && file.name.startsWith(`${name}_`)) ||
                      (name && lower.includes(name.toLowerCase())) ||
                      (id && lower.includes(id.toLowerCase()));
  
  // 按日期范围过滤
  if (reportDateFrom || reportDateTo) {
    const fileDate = new Date(file.date);
    if (reportDateFrom) {
      const fromDate = new Date(reportDateFrom);
      if (fileDate < fromDate) return false;  // 早于起始日期则过滤掉
    }
    if (reportDateTo) {
      const toDate = new Date(reportDateTo);
      toDate.setDate(toDate.getDate() + 1);  // 包含结束日期的整个一天
      if (fileDate >= toDate) return false;   // 晚于结束日期则过滤掉
    }
  }
  
  return true;
}
```

2. **handleReportDateFilterChange()** - 日期过滤变更处理
```typescript
function handleReportDateFilterChange() {
  if (reportPatient) {
    // 重新调用过滤函数，应用新的日期条件
    setReportFiles(filterReportsForPatient(reportFiles, reportPatient));
  }
}
```

3. **handleOpenReportHistory()** - 打开报告历史时重置日期过滤
```typescript
async function handleOpenReportHistory(patient: Patient) {
  setReportDateFrom("");  // 重置日期范围
  setReportDateTo("");
  // ... 加载报告文件
}
```

**UI组件**:
```tsx
{/* 日期范围过滤器 */}
<div className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
  <h3 className="mb-3 text-sm font-semibold text-slate-900">按日期搜索</h3>
  <div className="flex flex-wrap gap-3">
    {/* 起始日期输入 */}
    <input
      type="date"
      value={reportDateFrom}
      onChange={(e) => {
        setReportDateFrom(e.target.value);
        handleReportDateFilterChange();
      }}
    />
    
    {/* 结束日期输入 */}
    <input
      type="date"
      value={reportDateTo}
      onChange={(e) => {
        setReportDateTo(e.target.value);
        handleReportDateFilterChange();
      }}
    />
    
    {/* 重置按钮 */}
    <button
      onClick={() => {
        setReportDateFrom("");
        setReportDateTo("");
        if (reportPatient) {
          setReportFiles(filterReportsForPatient(reportFiles, reportPatient));
        }
      }}
    >
      重置过滤
    </button>
  </div>
</div>

{/* 匹配结果统计 */}
{reportFiles.length > 0 && (
  <div className="mb-3 text-xs text-slate-500">
    共找到 {reportFiles.length} 个匹配的报告文件
  </div>
)}
```

### 后端支持 (Backend)

**文件**: `ingestion/app/main.py`

**API端点** (已存在):
```python
@app.get("/reports")
def list_reports(date: str | None = None):
    """
    获取报告列表
    参数:
      - date (可选): YYYY-MM-DD格式，返回该日期的报告
    返回: ReportFile数组，按更新时间倒序
    """
    return _list_reports(date=date)
```

**文件系统结构**:
```
/data/reports/
├── 2026-02-10/
│   ├── 张三_20260210_090000.docx
│   └── 李四_20260210_140000.docx
├── 2026-02-11/
│   ├── 张三_20260211_170700.docx
│   └── 王五_20260211_100000.docx
└── 2026-02-12/
    └── 张三_20260212_093000.docx
```

---

## 使用流程

### 用户操作步骤

1. **打开患者列表** → 患者管理页面
2. **点击患者的"报告"按钮** → 打开报告历史模态框
3. **报告列表加载完成** → 显示所有该患者的报告
4. **设置起始日期** (可选) → 例如 2026-02-10
5. **设置结束日期** (可选) → 例如 2026-02-11
6. **实时过滤显示** → 只显示该日期范围内的报告
7. **点击报告进行操作**:
   - 预览 DOCX 文件
   - 打印报告
   - 下载报告

### 日期过滤逻辑

```
输入: 
  - 起始日期: 2026-02-10
  - 结束日期: 2026-02-11
  - 所有报告日期: [2026-02-09, 2026-02-10, 2026-02-11, 2026-02-12]

过滤过程:
  ✓ 2026-02-10: 2026-02-10 >= 2026-02-10 && 2026-02-10 < 2026-02-12 → 保留
  ✓ 2026-02-11: 2026-02-11 >= 2026-02-10 && 2026-02-11 < 2026-02-12 → 保留
  ✗ 2026-02-09: 2026-02-09 < 2026-02-10 → 过滤掉
  ✗ 2026-02-12: 2026-02-12 >= 2026-02-12 → 过滤掉

结果: [2026-02-10, 2026-02-11]
```

**特殊情况**:
- 只设置起始日期 → 显示该日期之后的所有报告
- 只设置结束日期 → 显示该日期之前的所有报告
- 都不设置 → 显示所有报告
- 起始日期 > 结束日期 → 显示为空（前端可增加验证）

---

## 测试场景

### 场景1: 基本日期范围搜索
```
患者: 张三
操作: 
  1. 打开报告历史
  2. 选择起始日期: 2026-02-10
  3. 选择结束日期: 2026-02-11
  
预期结果:
  ✓ 显示该日期范围内的报告
  ✓ 显示"共找到 X 个匹配的报告文件"
  ✓ 可以对每个报告进行预览/打印/下载
```

### 场景2: 只选择起始日期
```
操作: 
  1. 打开报告历史
  2. 选择起始日期: 2026-02-11
  3. 不选择结束日期
  
预期结果:
  ✓ 显示 2026-02-11 及之后的所有报告
```

### 场景3: 重置过滤
```
操作:
  1. 已设置日期范围过滤
  2. 点击"重置过滤"按钮
  
预期结果:
  ✓ 日期输入框清空
  ✓ 显示该患者的所有报告
```

### 场景4: 无匹配报告
```
操作:
  1. 选择起始日期和结束日期
  2. 该范围内没有报告
  
预期结果:
  ✓ 显示"暂无匹配的历史报告文件"
```

---

## 技术要点

### 日期比较
```typescript
// JavaScript Date 对象的比较
const fileDate = new Date("2026-02-11");
const fromDate = new Date("2026-02-10");
const toDate = new Date("2026-02-12");

fileDate >= fromDate && fileDate < toDate  // true
```

### 日期字符串处理
```typescript
// HTML5 date input 返回 YYYY-MM-DD 格式
const dateString = "2026-02-11";
const date = new Date(dateString);  // 注意: 转换为UTC
// 为了避免时区问题，直接字符串比较也可行
```

### 包含结束日期的方法
```typescript
// 方法1: 时间戳比较
toDate.setDate(toDate.getDate() + 1);  // 推进到第二天
if (fileDate < toDate) { /* 包含在内 */ }

// 方法2: 字符串比较 (更简单)
if (dateString <= endDateString) { /* 包含在内 */ }
```

---

## 性能考虑

### 过滤性能
- 前端过滤：O(n)，其中 n 是报告文件数量
- 对于大多数场景（<1000个报告），直接前端过滤足够快
- 如果报告数量 > 10000，考虑后端分页 + 日期范围查询

### 建议优化
```typescript
// 后期改进: 后端分页查询
async function fetchReportsInDateRange(dateFrom, dateTo) {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
    page: 1,
    limit: 50
  });
  
  const response = await fetch(`${API_BASE}/reports?${params}`);
  return response.json();
}
```

---

## 后续改进 (Future Enhancements)

### 短期 (v1.1)
- [ ] 前端日期验证（起始日期不能晚于结束日期）
- [ ] 快速日期快捷键 (今天、本周、本月)
- [ ] 日期范围选择器组件优化

### 中期 (v1.2)
- [ ] 后端支持日期范围查询参数
- [ ] 报告列表分页加载
- [ ] 导出日期范围内的所有报告为ZIP

### 长期 (v2.0)
- [ ] 批量操作 (选中多个报告进行批量打印/下载/删除)
- [ ] 高级搜索 (文件名关键词 + 日期范围 + 文件大小)
- [ ] 报告统计分析 (按日期统计上传数量)

---

## 代码示例

### 完整的使用流程 (前端)

```typescript
// 1. 患者点击"报告"按钮
function handleReportClick(patient: Patient) {
  handleOpenReportHistory(patient);
  // → setShowReportModal(true)
  // → 加载所有该患者的报告
}

// 2. 用户选择日期范围
function handleStartDateChange(e: React.ChangeEvent<HTMLInputElement>) {
  setReportDateFrom(e.target.value);
  handleReportDateFilterChange();
  // → 重新过滤报告列表
}

// 3. 显示过滤后的报告
function renderFilteredReports() {
  return reportFiles.map(file => (
    <tr key={file.name}>
      <td>{file.name}</td>
      <td>{file.date}</td>
      <td>{formatFileSize(file.size_bytes)}</td>
      <td>
        <button onClick={() => handlePreviewReport(file)}>预览</button>
        <button onClick={() => handlePrintReport(file)}>打印</button>
        <a href={buildReportDownloadUrl(file)}>下载</a>
      </td>
    </tr>
  ));
}
```

---

## 验收检查清单

- [x] 前端显示日期范围选择器
- [x] 前端实现日期范围过滤逻辑
- [x] 显示过滤结果统计
- [x] 提供"重置过滤"功能
- [x] 打开报告历史时重置日期过滤
- [x] 更新需求矩阵
- [x] 更新API文档
- [x] 编写功能文档
- [ ] 编写单元测试 (待实现)
- [ ] 进行集成测试 (待实现)
- [ ] 用户验收测试 (待实现)

---

**最后更新**: 2026-02-12  
**状态**: ✅ 已完成
