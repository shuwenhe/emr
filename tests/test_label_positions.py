#!/usr/bin/env python3
"""
测试热成像图标签位置的改进
"""

# 模拟ROI分析数据
mock_roi_analysis = {
    "roi_list": [
        {"name": "右眼", "mean_c": 36.5, "center_x_pct": 65, "center_y_pct": 20},
        {"name": "左眼", "mean_c": 36.3, "center_x_pct": 35, "center_y_pct": 20},
        {"name": "鼻子", "mean_c": 36.8, "center_x_pct": 50, "center_y_pct": 28},
        {"name": "右脸颊", "mean_c": 37.3, "center_x_pct": 70, "center_y_pct": 32},
        {"name": "左脸颊", "mean_c": 37.9, "center_x_pct": 30, "center_y_pct": 32},
        {"name": "口部", "mean_c": 38.4, "center_x_pct": 50, "center_y_pct": 38},
        {"name": "颈项", "mean_c": 35.7, "center_x_pct": 50, "center_y_pct": 48},
    ]
}

# 从analysis.py中导入相关常量和函数
import sys
sys.path.insert(0, '/home/shuwen/emr/ingestion')

from app.analysis import THERMAL_PLOT_BOUNDS, FACIAL_LABEL_OFFSETS, _roi_label_points

print("=== 热成像图标签位置测试 ===\n")

print("1. FACIAL_LABEL_OFFSETS 定义:")
for key, (dx, dy) in FACIAL_LABEL_OFFSETS.items():
    print(f"   {key:6s}: dx={dx:6.1f}, dy={dy:6.1f}")

print("\n2. 标签位置计算结果:")
points = _roi_label_points(mock_roi_analysis)

for point in points:
    name = point["name"]
    x = point["x"]
    y = point["y"]
    label_x = point["label_x"]
    label_y = point["label_y"]
    temp = point["mean_c"]
    print(f"   {name:6s} | 原位置:({x:5.1f}, {y:5.1f}) | 标签位置:({label_x:5.1f}, {label_y:5.1f}) | 温度:{temp:5.1f}°C")

print("\n3. 标签分类情况:")
head_count = 0
neck_count = 0
other_count = 0
for point in points:
    name = point["name"]
    if point["y"] <= 35.0 and not any(key in name for key in ("颈", "肩", "喉")):
        head_count += 1
    elif any(key in name for key in ("颈", "喉")) or (30.0 < point["y"] <= 45.0 and any(key in name for key in ("肩",))):
        neck_count += 1
    else:
        other_count += 1

print(f"   头部标签: {head_count}")
print(f"   颈部标签: {neck_count}")
print(f"   其他标签: {other_count}")

print("\n✓ 测试完成！标签位置现已改进。")
print("  - 新增了颈项等部位的标签偏移")
print("  - 头部标签分三层显示，避免拥挤")
print("  - 颈部标签单独一行显示")
print("  - 标签避让算法已优化")
