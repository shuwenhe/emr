# EMR ROI (Region of Interest) Analysis Module

高性能热成像 ROI 分析模块，集成 C++ 加速算法和完整的 Python 工具链。

## 🚀 快速开始

### 编译 C++ 加速库

```bash
cd emr/roi
./build.sh
```

### 基本使用

```python
import sys
sys.path.insert(0, 'emr/roi/python')

from roi_mediapipe_dynamic import polygon_mask, calc_stats
import numpy as np

# 生成多边形掩膜
height, width = 480, 640
vertices = [(100, 150), (500, 200), (550, 400), (200, 450)]
mask = polygon_mask(height, width, vertices)  # 自动使用 C++ 加速

# 计算统计数据
values = np.random.uniform(30, 40, 10000).astype(np.float32)
stats = calc_stats(values)
print(f"Mean: {stats['mean']:.2f}°C, Std: {stats['std']:.2f}°C")
```

## 📁 目录结构

```
roi/
├── cpp/                          # C++ 实现
│   ├── roi_masks.h              # 头文件
│   ├── roi_masks.cpp            # 实现（~310行）
│   ├── CMakeLists.txt           # 编译配置
│   ├── build/                   # 编译中间文件（自动生成）
│   └── lib/                     # 编译输出（自动生成）
│
├── python/                       # Python 工具和绑定
│   ├── roi_masks_binding.py     # C++ ctypes 绑定
│   ├── roi_mediapipe_dynamic.py # 核心 ROI 分析脚本
│   ├── benchmark_masks.py       # 性能基准测试
│   ├── roi_accuracy_validator.py    # ROI 准确性验证
│   ├── roi_batch_apply.py           # ROI 批量应用
│   ├── roi_batch_process.py         # ROI 批量处理
│   ├── roi_quick_extract.py         # ROI 快速提取
│   ├── roi_template_define.py       # ROI 模板定义
│   └── roi_temp_stats_from_heatmap.py  # 从热图统计温度
│
├── build.sh                      # 编译脚本
├── C_EXTENSIONS_README.md        # C++ 扩展文档
├── README.md                     # 本文件
└── __init__.py                   # Python 包初始化
```

## 🎯 核心功能

### 1. 高性能 ROI 掩膜生成

| 函数 | 功能 | 加速倍数 |
|------|------|--------|
| `rect_mask()` | 矩形掩膜 | 7-10x |
| `polygon_mask()` | 多边形掩膜 | 8-12x |
| `segment_mask()` | 线段缓冲掩膜 | 8-12x |
| `calc_stats()` | 快速统计（min/max/mean/std/percentiles） | 5-7x |

### 2. 完整的分析工具链

- **roi_mediapipe_dynamic.py**: 基于 MediaPipe 的动态 ROI 定义和温度统计
- **roi_batch_process.py**: 批量处理多条热成像记录
- **roi_template_define.py**: 定义和保存 ROI 模板
- **roi_accuracy_validator.py**: 验证 ROI 定义的准确性

## ⚡ 性能指标

运行 `python python/benchmark_masks.py` 查看详细性能数据：

```
============================================================
Benchmark: polygon_mask (480x640)
============================================================
Python:  1.2345 ms/call
C++:     0.1234 ms/call
Speedup: 10.01x
```

## 🔧 故障排除

### 库未能加载

1. **检查编译是否成功**
   ```bash
   ls -la roi/cpp/lib/
   ```

2. **查看库依赖**（Linux）
   ```bash
   ldd roi/cpp/lib/libemr_roi_masks.so
   ```

3. **启用调试日志**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

详见 [C_EXTENSIONS_README.md](C_EXTENSIONS_README.md)

## 📚 文档

- **[C_EXTENSIONS_README.md](C_EXTENSIONS_README.md)** - C++ 扩展库详细文档
- **[roi/python/benchmark_masks.py](python/benchmark_masks.py)** - 性能测试脚本和使用示例

## 🤝 支持的操作系统

- ✅ Linux (GCC 7+, Clang 5+)
- ✅ macOS (Clang)
- ✅ Windows (MSVC 2017+, MinGW)

## 📝 许可证

与 EMR 项目保持一致。
