#!/usr/bin/env python3
"""
性能基准测试：Python vs C++ ROI掩膜生成
"""

import time
import numpy as np
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入Python原生实现和C++版本
# 支持相对导入（模块方式）和直接导入（脚本方式）
try:
    from .roi_mediapipe_dynamic import (
        rect_mask, polygon_mask, segment_mask, calc_stats, Pt,
        C_LIB_AVAILABLE
    )
except (ImportError, ValueError):
    from roi_mediapipe_dynamic import (
        rect_mask, polygon_mask, segment_mask, calc_stats, Pt,
        C_LIB_AVAILABLE
    )

# 也导入C++直接绑定，用于对比
try:
    from .roi_masks_binding import (
        rect_mask_c, polygon_mask_c, segment_mask_c,
        calc_stats_fast_c
    )
except (ImportError, ValueError):
    try:
        from roi_masks_binding import (
            rect_mask_c, polygon_mask_c, segment_mask_c,
            calc_stats_fast_c
        )
    except ImportError:
        rect_mask_c = None
        polygon_mask_c = None
        segment_mask_c = None
        calc_stats_fast_c = None


def benchmark_rect_mask(height=480, width=640, runs=100):
    """基准测试：矩形掩膜生成"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmark: rect_mask ({height}x{width})")
    logger.info(f"{'='*60}")
    
    x1, y1, x2, y2 = 100.5, 150.3, 300.7, 350.2
    
    # Python 版本（总是有的）
    start = time.perf_counter()
    for _ in range(runs):
        mask = rect_mask(height, width, x1, y1, x2, y2)
    python_time = (time.perf_counter() - start) / runs * 1000
    logger.info(f"Python:  {python_time:.4f} ms/call")
    
    # C++ 版本（如果可用）
    if C_LIB_AVAILABLE and rect_mask_c:
        start = time.perf_counter()
        for _ in range(runs):
            mask_bytes = rect_mask_c(height, width, x1, y1, x2, y2)
        cpp_time = (time.perf_counter() - start) / runs * 1000
        logger.info(f"C++:     {cpp_time:.4f} ms/call")
        speedup = python_time / cpp_time
        logger.info(f"Speedup: {speedup:.2f}x")
    else:
        logger.info("C++ library not available")


def benchmark_polygon_mask(height=480, width=640, runs=100):
    """基准测试：多边形掩膜生成"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmark: polygon_mask ({height}x{width})")
    logger.info(f"{'='*60}")
    
    vertices = [
        (100, 150),
        (500, 200),
        (550, 400),
        (200, 450),
    ]
    
    # Python 版本
    start = time.perf_counter()
    for _ in range(runs):
        mask = polygon_mask(height, width, vertices)
    python_time = (time.perf_counter() - start) / runs * 1000
    logger.info(f"Python:  {python_time:.4f} ms/call")
    
    # C++ 版本
    if C_LIB_AVAILABLE and polygon_mask_c:
        start = time.perf_counter()
        for _ in range(runs):
            mask_bytes = polygon_mask_c(height, width, vertices)
        cpp_time = (time.perf_counter() - start) / runs * 1000
        logger.info(f"C++:     {cpp_time:.4f} ms/call")
        speedup = python_time / cpp_time
        logger.info(f"Speedup: {speedup:.2f}x")
    else:
        logger.info("C++ library not available")


def benchmark_segment_mask(height=480, width=640, runs=100):
    """基准测试：线段掩膜生成"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmark: segment_mask ({height}x{width})")
    logger.info(f"{'='*60}")
    
    p1 = Pt(100.5, 150.3)
    p2 = Pt(500.7, 400.2)
    thickness = 4.0
    
    # Python 版本
    start = time.perf_counter()
    for _ in range(runs):
        mask = segment_mask(height, width, p1, p2, thickness)
    python_time = (time.perf_counter() - start) / runs * 1000
    logger.info(f"Python:  {python_time:.4f} ms/call")
    
    # C++ 版本
    if C_LIB_AVAILABLE and segment_mask_c:
        start = time.perf_counter()
        for _ in range(runs):
            mask_bytes = segment_mask_c(height, width, p1.x, p1.y, p2.x, p2.y, thickness)
        cpp_time = (time.perf_counter() - start) / runs * 1000
        logger.info(f"C++:     {cpp_time:.4f} ms/call")
        speedup = python_time / cpp_time
        logger.info(f"Speedup: {speedup:.2f}x")
    else:
        logger.info("C++ library not available")


def benchmark_calc_stats(count=10000, runs=1000):
    """基准测试：统计计算"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmark: calc_stats (n={count})")
    logger.info(f"{'='*60}")
    
    values = np.random.normal(36.5, 1.2, size=count).astype(np.float32)
    
    # Python 版本
    start = time.perf_counter()
    for _ in range(runs):
        stats = calc_stats(values)
    python_time = (time.perf_counter() - start) / runs * 1000
    logger.info(f"Python:  {python_time:.4f} ms/call")
    
    # C++ 版本
    if C_LIB_AVAILABLE and calc_stats_fast_c:
        start = time.perf_counter()
        for _ in range(runs):
            stats = calc_stats_fast_c(values)
        cpp_time = (time.perf_counter() - start) / runs * 1000
        logger.info(f"C++:     {cpp_time:.4f} ms/call")
        speedup = python_time / cpp_time
        logger.info(f"Speedup: {speedup:.2f}x")
    else:
        logger.info("C++ library not available")


def benchmark_roi_pipeline(height=480, width=640, num_rois=14, runs=10):
    """基准测试：完整ROI生成流程（14个ROI）"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmark: Full ROI pipeline ({num_rois} ROIs, {height}x{width})")
    logger.info(f"{'='*60}")
    
    # 模拟14个ROI的掩膜生成
    vertices_list = [
        [(100, 150), (300, 180), (320, 300), (90, 280)],
        [(350, 160), (500, 180), (510, 300), (360, 280)],
        [(150, 320), (450, 330), (460, 450), (140, 440)],
    ]
    segments_list = [
        (Pt(100, 150), Pt(300, 300), 4),
        (Pt(350, 160), Pt(500, 300), 4),
        (Pt(150, 320), Pt(450, 450), 5),
    ] * 4  # 模拟12个线段
    
    # Python 版本
    start = time.perf_counter()
    for _ in range(runs):
        for verts in vertices_list:
            m1 = polygon_mask(height, width, verts)
        for p1, p2, th in segments_list:
            m2 = segment_mask(height, width, p1, p2, th)
    python_time = (time.perf_counter() - start) / runs * 1000
    logger.info(f"Python:  {python_time:.4f} ms/call (total for {num_rois} ROIs)")
    
    # C++ 版本
    if C_LIB_AVAILABLE and polygon_mask_c and segment_mask_c:
        start = time.perf_counter()
        for _ in range(runs):
            for verts in vertices_list:
                m1 = polygon_mask_c(height, width, verts)
            for p1, p2, th in segments_list:
                m2 = segment_mask_c(height, width, p1.x, p1.y, p2.x, p2.y, th)
        cpp_time = (time.perf_counter() - start) / runs * 1000
        logger.info(f"C++:     {cpp_time:.4f} ms/call (total for {num_rois} ROIs)")
        speedup = python_time / cpp_time
        logger.info(f"Speedup: {speedup:.2f}x")
    else:
        logger.info("C++ library not available (using Python fallback)")


if __name__ == "__main__":
    logger.info(f"C++ Library Available: {C_LIB_AVAILABLE}")
    logger.info(f"NumPy version: {np.__version__}")
    
    # 运行所有基准测试
    benchmark_rect_mask(runs=500)
    benchmark_polygon_mask(runs=200)
    benchmark_segment_mask(runs=200)
    benchmark_calc_stats(count=10000, runs=500)
    benchmark_roi_pipeline(num_rois=12, runs=50)
    
    logger.info(f"\n{'='*60}")
    logger.info("Benchmark completed!")
    logger.info(f"{'='*60}\n")
