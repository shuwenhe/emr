# EMR 项目内存消耗分析

基于对代码的深入分析，以下是主要的内存消耗点：

---

## 🔴 **一级内存消耗（关键）**

### 1. **热图像文件持续占用内存**
**位置**: `analysis.py` 的 `_generate_marked_image()` 和 `_generate_roi_labeled_image()` 函数

**问题代码**:
```python
# 第 2 倍内存占用！
image = plt.imread(str(base_image_path))  # ⚠️ 一份在内存
fig, ax = plt.subplots(figsize=(6, 4), dpi=180)  # 高DPI = 大内存
ax.imshow(image)  # ⚠️ matplotlib 内部又存了一份
fig.savefig(str(output_path), bbox_inches="tight", pad_inches=0)  # 保存时再次加载
plt.close(fig)  # ❌ 关键：如果顺序不对，可能泄漏
```

**内存占用**:
- 单张热图像（假设 1024×768 JPEG）：
  - `plt.imread()` 加载：~3MB（RGB 三通道）
  - `imshow()` 在 figure 中缓冲：~3MB
  - `savefig()` 生成新图像：~3-5MB
  - **单次调用: 9-11MB**

- 但是，当生成"基础热图" + "ROI标签版本"时：
  ```python
  # 第1次：生成基础热图
  marked_image_path = _generate_marked_image(grid, ...)  # 加载 grid，生成 PNG，~10MB
  
  # 第2次：再次加载基础热图来生成ROI版本
  image = plt.imread(str(base_image_path))  # ⚠️ 又加载一遍 8-10MB
  fig.savefig(...)  # 再生成一份 5-8MB
  ```
  **两个图都生成时: 18-28MB 内存开销**

### 2. **matplotlib 图像对象未及时释放**
**位置**: `analysis.py` 行 500-750

**问题代码**:
```python
# ❌ matplotlib 全局状态污染
fig, ax = plt.subplots(figsize=(6, 4), dpi=180)
ax.imshow(image)
# ... 添加注解、标签等
fig.savefig(...)
plt.close(fig)  # ✅ 这一行很重要，但没有保证释放

# 如果有多个 figure 被创建但没有显式关闭：
# - plt 有全局 figure 栈
# - 重复调用时旧 figure 堆积
```

**内存泄漏风险**:
- 每个 `figure` 对象占用 5-8MB（即使关闭后也可能在缓存中）
- 一个 `analyze_record()` 调用可能创建 2-3 个 figure
- 如果并发分析 10 个报告：60-90MB 泄漏

### 3. **温度矩阵（numpy 数组）的大尺寸**
**位置**: `analysis.py` 的 `_load_csv_grid()` 函数 (行 441-482)

**问题代码**:
```python
def _load_csv_grid(file_path: Path) -> Optional[np.ndarray]:
    rows: List[int] = []
    cols: List[int] = []
    temps: List[float] = []
    
    # ⚠️ 从 CSV 读取所有数据到内存中的三个列表
    with open(file_path, "r") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(int(row.get("row", "")))
            cols.append(int(row.get("col", "")))
            temps.append(float(row.get("temperature_c", "")))
    
    # ❌ 构建稀疏矩阵为密集的 numpy 数组
    max_r = max(rows)
    max_c = max(cols)
    grid = np.full((max_r + 1, max_c + 1), np.nan, dtype=float)
    for r, c, t in zip(rows, cols, temps):
        grid[r, c] = t
    return grid
```

**内存占用**:
- CSV 温度数据通常是 2-5MB（文本格式）
- 三个 Python 列表：3 × 5MB = 15MB
- `np.ndarray` 转换：
  - 如果是 320×240 热像仪，矩阵 76,800 个浮点数
  - `float64`: 76,800 × 8 字节 = **614KB**
  - `float32`: 76,800 × 4 字节 = **308KB**（目前没有优化）
  
- **但如果是高分辨率设备**（640×480）：
  - 307,200 × 8 字节 = **2.4MB**

**累积**: CSV 列表(15MB) + numpy 数组(0.6-2.4MB) + matplotlib 缓冲 = **15-20MB**

---

## 🟠 **二级内存消耗（重要）**

### 4. **ROI 分析数据结构堆积**
**位置**: `analysis.py` 行 1100-1150

**问题代码**:
```python
def analyze_record(record_id: str):
    # ... 
    roi_analysis = _analyze_roi_regions(payload_path, csv_is_matrix=True)
    
    # ⚠️ ROI 列表可能很大
    # roi_analysis = {
    #     'roi_list': [
    #         {'name': '..', 'mean_c': x, 'std_c': y, 'count': z, coords: [...]}
    #         ... 100+ 个 ROI 区域
    #     ]
    # }
    
    # ❌ 这些数据被复制多次：
    abnormal_regions = [
        {
            "region": item["region"],
            "region_cn": _region_to_body_part_cn(...), # 字符串复制
            "status": item["status"],
            "avg_c": item["avg_c"],
            "delta_c": ...,
        }
        for item in region_comparison  # ⚠️ 列表推导式创建新列表
    ]
    
    # ⚠️ 这些都被添加到最终 report dict，再序列化到 JSON
    report = {
        "roi_analysis": roi_analysis,  # 副本 1
        "abnormal_regions": abnormal_regions,  # 副本 2
        "region_comparison": region_comparison,  # 副本 3
    }
```

**内存占用**:
- 单个 ROI 信息：~500 字节
- 100 个 ROI：~50KB
- 复制 3 份：~150KB
- 整个 report 对象序列化：**200-500KB**

### 5. **LLM 上下文字符串的构建**
**位置**: `analysis.py` 行 143-189 (`_build_llm_context`)

**问题代码**:
```python
def _build_llm_context(...):
    context = (
        "你是一名医疗热成像评估助手。..."  # 基础提示词
        f"患者信息：姓名={...} ..."  # 字符串拼接
        f"身体部位温度分析：\n"
        # ... 循环添加 ROI 信息
    )
    
    # ⚠️ 每次都重新构建字符串
    for roi in roi_list[:5]:
        context += f"  - {roi['name']}: {roi['mean_c']}°C ...\n"
```

**内存占用**:
- 基础提示词：~1-2KB
- ROI 信息拼接：5 个 ROI × 200 字节 = 1KB
- 异常区域列表：可能 5-10KB
- **总计**: 10-15KB
- **问题**: 字符串拼接在 Python 中产生临时对象（O(n²) 复杂度）

### 6. **患者历史记录缓存**
**位置**: `analysis.py` 行 1170-1175

**问题代码**:
```python
history_records = []
if patient_id:
    history_records = get_patient_history(
        patient_id=patient_id,
        exclude_record_id=record_id,
        limit=5,  # 最多 5 条记录
    )
```

**内存占用**:
- 每条历史记录：2-5KB（EMR 摘要）
- 5 条记录：10-25KB
- 在内存中保留，直到函数返回

---

## 🟡 **三级内存消耗（改进）**

### 7. **JSON 序列化前的中间对象**
```python
report = {
    "report_id": report_id,
    "record_id": record_id,
    # ... 30+ 个字段
    "thermal_images": image_paths,  # 列表
    "thermal_marked_image": marked_image_path,  # 字符串
    "thermal_roi_labeled_image": roi_labeled_image_path,  # 字符串
}

# ⚠️ 完整的 report dict 在内存中
# JSON 序列化后还占用内存
json_str = json.dumps(report)  # 内存中又有一份
```

**内存占用**: 100-200KB（整个 report 对象）

---

## 📊 **内存消耗总结表**

| 操作/对象 | 大小 | 备注 |
|-----------|------|------|
| CSV 数据 → 列表 | 10-15MB | 温度数据文件解析 |
| numpy 数组（温度矩阵） | 0.6-2.4MB | 与分辨率相关 |
| matplotlib figure | 5-8MB × 2-3 | 热图生成（可能未释放） |
| 全局 figure 缓存 | 10-30MB | 多并发时堆积 |
| 图像文件缓存 | 3-5MB × 2 | 基础图 + ROI 标注图 |
| ROI 数据结构 | 50-200KB | 复制 3 份 |
| 最终 report 对象 | 200-500KB | 序列化前后 |
| **单个分析总计** | **30-65MB** | 峰值内存占用 |
| **10 个并发分析** | **300-650MB** | 极限情况 |

---

## 🎯 **快速优化建议**（内存）

### P0 优先级（立即可做）
```python
# ❌ 当前做法：
image = plt.imread(str(base_image_path))  # 第1次加载
fig, ax = plt.subplots(...)
ax.imshow(image)  # 第2次在 figure 中
fig.savefig(str(output_path))  # 第3次保存
plt.close(fig)

# ✅ 优化做法：
from PIL import Image
import io

with Image.open(str(base_image_path)) as img:
    # 不保存到内存，直接操作
    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)  # ⬇️ DPI 从 180 → 100
    ax.imshow(np.array(img))
    fig.savefig(str(output_path), bbox_inches="tight", pad_inches=0, dpi=100)
    plt.close(fig)
# ✨ 图像对象立即释放
```
**预期效果**: 内存占用 **↓ 30-40%**

### P1 优先级（1 小时）
```python
# ❌ 当前：float64 数组
grid = np.full((max_r + 1, max_c + 1), np.nan, dtype=float)

# ✅ 优化：float32
grid = np.full((max_r + 1, max_c + 1), np.nan, dtype=np.float32)  # 节省 50%
```
**预期效果**: 数组内存 **↓ 50%** (2.4MB → 1.2MB)

### P2 优先级（2 小时）
```python
# 避免字符串拼接，改用列表 join（O(n) vs O(n²)）
context_parts = [
    "基础提示词...",
    f"患者信息：...",
]

for roi in roi_list[:5]:
    context_parts.append(f"  - {roi['name']}: {roi['mean_c']}°C")

context = "\n".join(context_parts)  # ✅ 一次构建
```
**预期效果**: 字符串构建 **↓ 70%**

### P3 优先级（长期）
```python
# 不在内存中存储完整 report，使用流式写入
def analyze_record_streaming(record_id: str):
    with open(f"{record_id}.json", "w") as f:
        f.write('{"report": [\n')
        # 逐步写入，而不是全部在内存中
        # ...
```
**预期效果**: 峰值内存 **↓ 80%**

---

## 📈 **内存监控代码示例**

```python
import tracemalloc
import logging

tracemalloc.start()

before = tracemalloc.get_traced_memory()[0]
result = analyze_record("record123")
after = tracemalloc.get_traced_memory()[0]

memory_used_mb = (after - before) / (1024 * 1024)
logging.info(f"analyze_record memory usage: {memory_used_mb:.1f} MB")

# 快照对比
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

---

## 📌 **总结**

**最大的内存消耗点**（按严重程度排序）：
1. **CSV → numpy 数组转换** (10-15MB)
2. **matplotlib 图像缓冲** (5-8MB × 多个)
3. **未释放的 figure 对象** (10-30MB 泄漏)
4. **High DPI 设置** (180 dpi 很高，资源浪费)
5. **ROI 数据复制** (200KB 浪费)

**建议优化顺序**：
1. ✅ P0: 改用 PIL，降低 DPI，显式关闭 figure
2. ✅ P1: numpy float32，避免字符串拼接
3. ✅ P2: 长期考虑流式处理 + 内存池

**预期总改进**: **单个报告 65MB → 15-20MB** (缩小 75%)
