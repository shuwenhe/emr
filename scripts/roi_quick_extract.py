#!/usr/bin/env python3
"""
Quick ROI extraction with predefined standard body regions.
Automatically applies standard anatomical ROI to thermal matrix.

Usage:
python3 scripts/roi_quick_extract.py \
  --matrix-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1.csv \
  --out-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1_quick_roi.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MplPath


def polygon_mask(height: int, width: int, vertices: list[tuple[float, float]]) -> np.ndarray:
    """Create binary mask for polygon ROI."""
    path = MplPath(vertices)
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    points = np.vstack((xx.ravel(), yy.ravel())).T
    mask = path.contains_points(points, radius=0.5)
    return mask.reshape((height, width))


def rect_mask(height: int, width: int, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    """Create binary mask for rectangular ROI."""
    mask = np.zeros((height, width), dtype=bool)
    x1, x2 = int(np.clip(min(x1, x2), 0, width-1)), int(np.clip(max(x1, x2), 0, width-1))
    y1, y2 = int(np.clip(min(y1, y2), 0, height-1)), int(np.clip(max(y1, y2), 0, height-1))
    mask[y1:y2+1, x1:x2+1] = True
    return mask


def get_standard_rois(height: int, width: int) -> dict[str, np.ndarray]:
    """
    Define standard anatomical ROI for thermal imaging.
    Based on typical frontal human thermal image proportions.
    
    Assumes:
      - Y: 0=top (head) -> height=bottom (feet)
      - X: 0=left -> width=right
    """
    rois: dict[str, np.ndarray] = {}
    
    h_third = height // 3
    h_quarter = height // 4
    
    w_third = width // 3
    w_quarter = width // 4
    w_half = width // 2
    
    # Head region (top 20%)
    head_h = int(height * 0.2)
    rois["额头"] = rect_mask(height, width, 
                                  int(w_half - w_quarter), 0,
                                  int(w_half + w_quarter), head_h)
    
    # Eyes region
    eye_y_low = int(height * 0.15)
    eye_y_high = int(height * 0.25)
    rois["左眼"] = rect_mask(height, width,
                                  int(w_quarter * 0.5), eye_y_low,
                                  int(w_quarter * 1.5), eye_y_high)
    rois["右眼"] = rect_mask(height, width,
                                   int(w_half + w_quarter * 0.5), eye_y_low,
                                   int(w_half + w_quarter * 1.5), eye_y_high)
    
    # Cheeks region
    cheek_y_low = int(height * 0.25)
    cheek_y_high = int(height * 0.4)
    rois["左脸颊"] = rect_mask(height, width,
                                    int(w_quarter * 0.2), cheek_y_low,
                                    int(w_quarter * 1.2), cheek_y_high)
    rois["右脸颊"] = rect_mask(height, width,
                                     int(w_half + w_quarter * 0.2), cheek_y_low,
                                     int(w_half + w_quarter * 1.2), cheek_y_high)
    
    # Nose region
    rois["鼻子"] = rect_mask(height, width,
                              int(w_half - w_quarter * 0.3), int(height * 0.3),
                              int(w_half + w_quarter * 0.3), int(height * 0.45))
    
    # Jaw/chin region
    rois["下巴"] = rect_mask(height, width,
                              int(w_quarter * 0.5), int(height * 0.4),
                              int(width - w_quarter * 0.5), int(height * 0.55))
    
    # Neck region
    rois["颈部"] = rect_mask(height, width,
                              int(w_quarter * 0.8), int(height * 0.5),
                              int(width - w_quarter * 0.8), int(height * 0.65))
    
    # Chest/torso upper region
    rois["胸部"] = rect_mask(height, width,
                               int(w_quarter * 0.5), int(height * 0.6),
                               int(width - w_quarter * 0.5), int(height * 0.8))
    
    # Abdomen region
    rois["腹部"] = rect_mask(height, width,
                                 int(w_quarter * 0.6), int(height * 0.75),
                                 int(width - w_quarter * 0.6), int(height * 0.9))
    
    # Left/right arm regions
    rois["左臂"] = rect_mask(height, width,
                                  0, int(height * 0.5),
                                  int(w_quarter * 0.8), int(height * 0.85))
    rois["右臂"] = rect_mask(height, width,
                                   int(width - w_quarter * 0.8), int(height * 0.5),
                                   width, int(height * 0.85))
    
    # Lower extremities
    rois["左腿"] = rect_mask(height, width,
                                  int(w_quarter * 0.5), int(height * 0.85),
                                  int(w_half - w_quarter * 0.2), height)
    rois["右腿"] = rect_mask(height, width,
                                   int(w_half + w_quarter * 0.2), int(height * 0.85),
                                   int(width - w_quarter * 0.5), height)
    
    return rois


def calc_stats(values: np.ndarray) -> dict[str, float]:
    """Calculate temperature statistics for ROI."""
    if values.size == 0:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
            "p05": 0.0,
            "p95": 0.0,
        }
    return {
        "count": int(values.size),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values)),
        "p05": float(np.percentile(values, 5)),
        "p95": float(np.percentile(values, 95)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="快速提取预定义的标准人体部位温度统计")
    parser.add_argument("--matrix-csv", required=True, help="温度矩阵CSV路径")
    parser.add_argument("--out-csv", help="输出统计CSV路径，默认同目录 *_quick_roi.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_csv = Path(args.matrix_csv)
    
    if not matrix_csv.exists():
        raise FileNotFoundError(f"未找到CSV: {matrix_csv}")
    
    out_csv = Path(args.out_csv) if args.out_csv else matrix_csv.with_name(f"{matrix_csv.stem}_quick_roi.csv")
    
    print(f"[INFO] 正在加载矩阵: {matrix_csv}")
    matrix = np.loadtxt(matrix_csv, delimiter=",")
    
    if matrix.ndim != 2:
        raise ValueError(f"CSV不是二维矩阵: shape={matrix.shape}")
    
    h, w = matrix.shape
    print(f"[INFO] 矩阵尺寸: {h} x {w}")
    
    rois = get_standard_rois(h, w)
    print(f"[INFO] 已定义 {len(rois)} 个标准ROI: {list(rois.keys())}")
    
    rows: list[dict] = []
    for roi_name, mask in rois.items():
        values = matrix[mask]
        if values.size == 0:
            print(f"  [WARN] ROI '{roi_name}' 没有覆盖到像素（空ROI）")
            stats = calc_stats(np.array([]))
        else:
            stats = calc_stats(values)
        
        row = {"roi_name": roi_name, **stats}
        rows.append(row)
        print(f"  ✓ {roi_name:15s} count={stats['count']:5d} mean={stats['mean']:6.2f}°C (min={stats['min']:5.2f}, max={stats['max']:5.2f}, std={stats['std']:5.2f})")
    
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["roi_name", "count", "min", "max", "mean", "median", "std", "p05", "p95"]
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\n[DONE] ROI统计已导出: {out_csv}")


if __name__ == "__main__":
    main()
