"""
ctypes 绑定：加载编译的C++ ROI掩膜库
"""

import ctypes
import os
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 设置库搜索路径
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_SEARCH_PATHS = [
    _SCRIPT_DIR / "lib",  # CMake build 输出
    _SCRIPT_DIR / "build" / "lib",
    _SCRIPT_DIR,  # 本地目录
]

if sys.platform == "win32":
    _LIB_NAMES = ["emr_roi_masks.dll", "emr_roi_masks.lib"]
elif sys.platform == "darwin":
    _LIB_NAMES = ["libemr_roi_masks.dylib", "libemr_roi_masks.so"]
else:  # Linux
    _LIB_NAMES = ["libemr_roi_masks.so", "libemr_roi_masks.so.1"]

_c_lib: Optional[ctypes.CDLL] = None


def _find_and_load_lib() -> Optional[ctypes.CDLL]:
    """尝试在搜索路径中找到并加载编译好的库"""
    global _c_lib
    
    if _c_lib is not None:
        return _c_lib
    
    # 尝试从各个path加载
    for search_path in _LIB_SEARCH_PATHS:
        if not search_path.exists():
            continue
        
        for lib_name in _LIB_NAMES:
            lib_path = search_path / lib_name
            if lib_path.exists():
                try:
                    _c_lib = ctypes.CDLL(str(lib_path))
                    logger.info(f"Successfully loaded emr_roi_masks from {lib_path}")
                    _setup_c_function_signatures()
                    return _c_lib
                except OSError as e:
                    logger.debug(f"Failed to load {lib_path}: {e}")
                    continue
    
    # 尝试直接加载（系统路径）
    for lib_name in _LIB_NAMES:
        try:
            _c_lib = ctypes.CDLL(lib_name)
            logger.info(f"Successfully loaded emr_roi_masks from system path: {lib_name}")
            _setup_c_function_signatures()
            return _c_lib
        except OSError:
            continue
    
    logger.warning("Failed to load emr_roi_masks C++ library; will use Python fallback")
    return None


def _setup_c_function_signatures():
    """配置C函数签名"""
    if _c_lib is None:
        return
    
    # rect_mask
    _c_lib.rect_mask.argtypes = [
        ctypes.c_int, ctypes.c_int,  # height, width
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,  # x1, y1, x2, y2
        ctypes.POINTER(ctypes.c_ubyte),  # mask_out
    ]
    _c_lib.rect_mask.restype = ctypes.c_int
    
    # polygon_mask
    _c_lib.polygon_mask.argtypes = [
        ctypes.c_int, ctypes.c_int,  # height, width
        ctypes.POINTER(ctypes.c_float),  # vertices
        ctypes.c_int,  # num_vertices
        ctypes.POINTER(ctypes.c_ubyte),  # mask_out
    ]
    _c_lib.polygon_mask.restype = ctypes.c_int
    
    # segment_mask
    _c_lib.segment_mask.argtypes = [
        ctypes.c_int, ctypes.c_int,  # height, width
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,  # x1, y1, x2, y2
        ctypes.c_float,  # thickness
        ctypes.POINTER(ctypes.c_ubyte),  # mask_out
    ]
    _c_lib.segment_mask.restype = ctypes.c_int
    
    # calc_stats_fast
    _c_lib.calc_stats_fast.argtypes = [
        ctypes.POINTER(ctypes.c_float),  # values
        ctypes.c_int,  # count
        ctypes.POINTER(ctypes.c_float),  # out_min
        ctypes.POINTER(ctypes.c_float),  # out_max
        ctypes.POINTER(ctypes.c_float),  # out_mean
        ctypes.POINTER(ctypes.c_float),  # out_median
        ctypes.POINTER(ctypes.c_float),  # out_std
        ctypes.POINTER(ctypes.c_float),  # out_p05
        ctypes.POINTER(ctypes.c_float),  # out_p95
    ]
    _c_lib.calc_stats_fast.restype = ctypes.c_int


def rect_mask_c(height: int, width: int, x1: float, y1: float, x2: float, y2: float) -> Optional[bytes]:
    """
    C++ 实现：生成矩形掩膜
    返回 bytes (uint8), 或 None 如果失败或库未加载
    """
    lib = _find_and_load_lib()
    if lib is None:
        return None
    
    try:
        mask = (ctypes.c_ubyte * (height * width))()
        ret = lib.rect_mask(height, width, x1, y1, x2, y2, mask)
        if ret == 0:
            return bytes(mask)
        return None
    except Exception as e:
        logger.debug(f"C++ rect_mask failed: {e}")
        return None


def polygon_mask_c(height: int, width: int, vertices: list) -> Optional[bytes]:
    """
    C++ 实现：生成多边形掩膜
    vertices: [(x0, y0), (x1, y1), ...]
    返回 bytes (uint8), 或 None 如果失败或库未加载
    """
    lib = _find_and_load_lib()
    if lib is None:
        return None
    
    try:
        # 展平顶点列表 [(x,y), ...] -> [x, y, x, y, ...]
        verts_flat = []
        for x, y in vertices:
            verts_flat.append(float(x))
            verts_flat.append(float(y))
        
        verts_array = (ctypes.c_float * len(verts_flat))(*verts_flat)
        mask = (ctypes.c_ubyte * (height * width))()
        
        ret = lib.polygon_mask(height, width, verts_array, len(vertices), mask)
        if ret == 0:
            return bytes(mask)
        return None
    except Exception as e:
        logger.debug(f"C++ polygon_mask failed: {e}")
        return None


def segment_mask_c(height: int, width: int, x1: float, y1: float, x2: float, y2: float,
                   thickness: float) -> Optional[bytes]:
    """
    C++ 实现：生成线段缓冲掩膜
    返回 bytes (uint8), 或 None 如果失败或库未加载
    """
    lib = _find_and_load_lib()
    if lib is None:
        return None
    
    try:
        mask = (ctypes.c_ubyte * (height * width))()
        ret = lib.segment_mask(height, width, x1, y1, x2, y2, thickness, mask)
        if ret == 0:
            return bytes(mask)
        return None
    except Exception as e:
        logger.debug(f"C++ segment_mask failed: {e}")
        return None


def calc_stats_fast_c(values) -> Optional[dict]:
    """
    C++ 实现：快速计算统计
    values: numpy array 或类似的可迭代，float32 首选
    返回 dict {'min', 'max', 'mean', 'median', 'std', 'p05', 'p95'} 或 None
    """
    lib = _find_and_load_lib()
    if lib is None:
        return None
    
    try:
        import numpy as np
        
        # 确保是 numpy array
        if not isinstance(values, np.ndarray):
            values = np.asarray(values, dtype=np.float32)
        elif values.dtype != np.float32:
            values = values.astype(np.float32)
        
        count = len(values)
        if count == 0:
            return None
        
        # 创建输出缓冲
        out_min = ctypes.c_float()
        out_max = ctypes.c_float()
        out_mean = ctypes.c_float()
        out_median = ctypes.c_float()
        out_std = ctypes.c_float()
        out_p05 = ctypes.c_float()
        out_p95 = ctypes.c_float()
        
        # 调用C++函数
        values_ptr = values.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        ret = lib.calc_stats_fast(
            values_ptr, count,
            ctypes.byref(out_min), ctypes.byref(out_max), ctypes.byref(out_mean),
            ctypes.byref(out_median), ctypes.byref(out_std),
            ctypes.byref(out_p05), ctypes.byref(out_p95)
        )
        
        if ret == 0:
            return {
                "min": out_min.value,
                "max": out_max.value,
                "mean": out_mean.value,
                "median": out_median.value,
                "std": out_std.value,
                "p05": out_p05.value,
                "p95": out_p95.value,
                "count": count,
            }
        return None
    except Exception as e:
        logger.debug(f"C++ calc_stats_fast failed: {e}")
        return None


def is_c_lib_available() -> bool:
    """检查C++库是否可用"""
    return _find_and_load_lib() is not None
