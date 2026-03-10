# EMR ROI Masks C++ 加速库

## 概述

本目录包含高性能的C++ ROI掩膜生成库，用于加速热成像分析系统中的关键计算步骤。

**预期性能提升**
- ROI掩膜生成（polygon_mask/segment_mask）：**8-12 倍**
- 统计计算（calc_stats）：**5-7 倍**
- 综合处理流程：**40-60% 总体时间减少**

## 文件结构

```
emr/roi/
├── cpp/                     # C++ 源代码目录
│   ├── roi_masks.h          # C++ 头文件（函数声明）
│   ├── roi_masks.cpp        # C++ 实现（~310行）
│   ├── CMakeLists.txt       # CMake 编译配置
│   ├── build/               # 编译中间文件（编译生成）
│   └── lib/                 # 编译输出库文件（编译生成）
├── python/                  # Python 文件目录
│   ├── roi_masks_binding.py         # Python ctypes 绑定
│   ├── roi_mediapipe_dynamic.py     # 主ROI分析脚本（已集成C++调用）
│   ├── benchmark_masks.py           # 性能基准测试
│   ├── roi_accuracy_validator.py    # ROI 准确性验证
│   ├── roi_batch_apply.py           # ROI 批量应用
│   ├── roi_batch_process.py         # ROI 批量处理
│   ├── roi_quick_extract.py         # ROI 快速提取
│   ├── roi_template_define.py       # ROI 模板定义
│   └── roi_temp_stats_from_heatmap.py  # 从热图统计温度
├── build.sh                 # 编译脚本（Linux/macOS）
└── C_EXTENSIONS_README.md   # 本文件
```

## 编译步骤

### 前置条件

- **C++17 编译器**：GCC 7+, Clang 5+, MSVC 2017+
- **CMake 3.10+**
- **Python 3.8+** 和 numpy

### Linux / macOS 编译

```bash
cd emr/roi

# 方案1：使用提供的脚本（推荐）
chmod +x build.sh
./build.sh

# 或者方案2：手动编译
mkdir -p cpp/build
cd cpp/build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . -j$(nproc)
cd ../..
```

### Windows 编译

```cmd
cd emr\roi

# 使用VS编译器
mkdir cpp\build
cd cpp\build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . --config Release -j%NUMBER_OF_PROCESSORS%
cd ..\..
```

### 编译结果

编译完成后，库文件会生成到：
- **Linux/macOS**: `emr/roi/cpp/lib/libemr_roi_masks.so`
- **Windows**: `emr/roi/cpp/lib/emr_roi_masks.dll`

## 使用方式

### 自动加载（推荐）

只需导入 `roi_mediapipe_dynamic.py`，它会自动检测和加载C++库：

```python
# 方式1：直接从 roi/python/ 目录导入
from roi.python.roi_mediapipe_dynamic import (
    rect_mask, polygon_mask, segment_mask, calc_stats
)

# 方式2：包含 roi/python/ 目录到PYTHONPATH后直接导入
import sys
sys.path.insert(0, 'emr/roi/python')
from roi_mediapipe_dynamic import (
    rect_mask, polygon_mask, segment_mask, calc_stats
)

# 使用方式与原来相同
mask = polygon_mask(480, 640, [(100, 150), (500, 200), (550, 400)])
stats = calc_stats(values_array)

# 如果C++库可用，会自动加速；否则fallback到Python
```

### 手动控制

如需检查C++库是否可用或直接调用C++版本：

```python
import sys
sys.path.insert(0, 'emr/roi/python')

from roi_masks_binding import (
    is_c_lib_available, rect_mask_c, polygon_mask_c, segment_mask_c
)

if is_c_lib_available():
    print("C++ library is available")
    mask_bytes = polygon_mask_c(480, 640, vertices)
else:
    print("Using Python fallback")
```

## 性能测试

运行性能基准测试：

```bash
cd emr/roi/python
python benchmark_masks.py
```

或者从 roi 目录：

```bash
cd emr/roi
python python/benchmark_masks.py
```

**示例输出**
```
============================================================
Benchmark: rect_mask (480x640)
============================================================
Python:  0.1234 ms/call
C++:     0.0156 ms/call
Speedup: 7.91x

============================================================
Benchmark: polygon_mask (480x640)
============================================================
Python:  1.2345 ms/call
C++:     0.1234 ms/call
Speedup: 10.01x

============================================================
Benchmark: segment_mask (480x640)
============================================================
Python:  0.8901 ms/call
C++:     0.1123 ms/call
Speedup: 7.93x

============================================================
Benchmark: calc_stats (n=10000)
============================================================
Python:  2.3456 ms/call
C++:     0.3789 ms/call
Speedup: 6.19x
```

## 调试与故障排除

### 库未能加载

如果C++库无法加载，检查以下几点：

1. **编译是否成功**
   ```bash
    ls -la emr/roi/cpp/lib/
    ls -la emr/roi/cpp/build/lib/
   ```
   确保库文件存在

2. **依赖库是否缺失**（Linux）
   ```bash
    ldd emr/roi/cpp/lib/libemr_roi_masks.so
   ```
   检查是否有缺失的依赖

3. **权限问题**
   ```bash
    chmod 755 emr/roi/cpp/lib/libemr_roi_masks.so
   ```

4. **PYTHONPATH 设置**
   ```bash
    export PYTHONPATH="${PYTHONPATH}:$(pwd)/emr/roi/python"
   ```

### 启用调试日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)

import sys
sys.path.insert(0, 'emr/roi/python')
from roi_masks_binding import is_c_lib_available
print(f"C++ Library Available: {is_c_lib_available()}")
```

### 强制使用Python版本

如果需要测试Python版本或故障排查，修改 `roi/python/roi_masks_binding.py` 中的全局变量：

```python
# 在 roi/python/roi_masks_binding.py 中
_c_lib = None  # 强制设置为 None
```

或在您的代码中：

```python
import sys
sys.path.insert(0, 'emr/roi/python')
import roi_masks_binding
roi_masks_binding._c_lib = None  # 禁用C++库

# 后续调用会自动使用Python fallback
from roi_mediapipe_dynamic import calc_stats
```

## 技术细节

### 算法优化

**矩形掩膜 (rect_mask)**
- 时间复杂度：O(面积)
- 直接内存写入，无额外分配

**多边形掩膜 (polygon_mask)**
- 射线法则（Ray Casting）
- 时间复杂度：O(h × w × n) where n = 顶点数，通常 n=4-8
- 优化：仅处理必要区域

**线段掩膜 (segment_mask)**
- 距离栅格化
- 时间复杂度：O(h × w)
- 优化：点积计算替代昂贵的平方根

**快速统计 (calc_stats_fast)**
- 单遍 min/max/mean/count
- Quickselect + 排序计算分位数
- 预期时间：O(n log n)，约Python版本的 1/5-1/7

### 内存优化

- 输出掩膜使用 `uint8_t` 布尔数组，而非numpy的 `bool_` (1字节)
- 避免中间数组复制
- 直接memset初始化

## 性能建议

### 什么时候值得用C++

- **掩膜生成频繁**：每个ROI × 每条记录 × 每天，累积效果显著
- **统计计算量大**：样本数 > 1000 点/ROI，收益明显
- **实时系统**：需要 < 100ms 延迟

### 什么时候用Python就够了

- 单次调用
- 小数据量（< 1000 点）
- 原型开发阶段

## 已知限制

1. **Windows 编译**需要MSVC或MinGW，GCC on Windows可能需要额外配置
2. **ARM 架构**（树莓派等）需自行编译
3. **Python版本**：仅支持 3.8+
4. **并发安全**：当前实现线程安全，但ctypes调用有GIL

## 未来改进

- [ ] 使用SIMD优化（SSE/AVX）
- [ ] OpenCL/CUDA 支持（GPU加速）
- [ ] pybind11 绑定（替代ctypes）
- [ ] 预编译二进制发布

## 许可

与EMR项目保持一致。

---

## 快速开始

```bash
# 1. 编译 C++ 库
cd emr/roi
./build.sh

# 2. 运行性能测试
python python/benchmark_masks.py

# 3. 在项目中使用（自动）
# 将以下代码添加到您的项目中
import sys
sys.path.insert(0, 'path/to/emr/roi/python')
from roi_mediapipe_dynamic import polygon_mask, calc_stats
# 库会自动检测并加载C++版本，或fallback到Python
```

**主要改进（相比原始结构）**
- ✅ 独立的 ROI 模块：所有 ROI 相关代码隔离在 `roi/` 目录
- ✅ C++ 文件独立管理：`roi/cpp/` 包含所有编译相关文件
- ✅ Python 文件独立管理：`roi/python/` 包含所有 Python 代码和工具脚本
- ✅ 编译输出隔离：库文件生成到 `roi/cpp/lib/`，避免混淆
- ✅ 向后兼容：自动库发现机制，无需修改现有代码
- ✅ 易于维护：清晰的目录结构，便于后续扩展
- ✅ 模块化设计：便于将 ROI 功能作为子模块共享或版本管理

有问题？查看 `roi/python/benchmark_masks.py` 了解使用示例。
