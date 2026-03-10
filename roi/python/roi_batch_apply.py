#!/usr/bin/env python3
"""
Batch apply ROI template to multiple thermal matrices and export summary.

Usage:
python3 roi/python/roi_batch_apply.py \
  --template-json data/35/2/roi_template.json \
  --matrix-dir data/35/2 \
  --out-summary data/35/2/roi_batch_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
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


def calc_stats(values: np.ndarray) -> dict[str, float]:
    """Calculate temperature statistics for ROI."""
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


def apply_template_to_matrix(matrix: np.ndarray, roi_polygons: list[dict]) -> dict[str, dict[str, float]]:
    """Apply ROI polygons to matrix and return stats per ROI."""
    h, w = matrix.shape
    result: dict[str, dict[str, float]] = {}

    for item in roi_polygons:
        name = item["name"]
        vertices = item["vertices"]
        mask = polygon_mask(h, w, vertices)
        values = matrix[mask]

        if values.size == 0:
            print(f"  [WARN] ROI '{name}' 没有覆盖到有效像素。")
            continue

        result[name] = calc_stats(values)

    return result


def find_matrix_csvs(matrix_dir: Path, pattern: str = "*.csv") -> list[Path]:
    """Find all matrix CSV files in directory."""
    files = sorted(matrix_dir.glob(pattern))
    return [f for f in files if "_roi_stats" not in f.name and f.is_file()]


def load_template(template_json: Path) -> list[dict]:
    """Load ROI template from JSON."""
    with template_json.open("r", encoding="utf-8") as f:
        return json.load(f)


def export_summary(summary_data: list[dict], out_csv: Path) -> None:
    """Export batch summary to CSV (wide format: matrix vs ROI).
    
    Format:
      matrix_name | roi1_mean | roi1_count | roi2_mean | roi2_count | ...
    """
    if not summary_data:
        raise RuntimeError("没有可导出的汇总数据。")

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Prepare fieldnames
    fieldnames = ["matrix_name"]
    roi_names: set[str] = set()
    for row in summary_data:
        roi_names.update(k for k in row.keys() if k != "matrix_name")
    
    for roi_name in sorted(roi_names):
        fieldnames.extend([
            f"{roi_name}_count",
            f"{roi_name}_min",
            f"{roi_name}_max",
            f"{roi_name}_mean",
            f"{roi_name}_median",
            f"{roi_name}_std",
            f"{roi_name}_p05",
            f"{roi_name}_p95",
        ])

    # Flatten stats into single row per matrix
    flattened_rows: list[dict] = []
    for row in summary_data:
        flat = {"matrix_name": row["matrix_name"]}
        for roi_name in sorted(roi_names):
            if roi_name in row:
                stats = row[roi_name]
                flat[f"{roi_name}_count"] = stats["count"]
                flat[f"{roi_name}_min"] = stats["min"]
                flat[f"{roi_name}_max"] = stats["max"]
                flat[f"{roi_name}_mean"] = stats["mean"]
                flat[f"{roi_name}_median"] = stats["median"]
                flat[f"{roi_name}_std"] = stats["std"]
                flat[f"{roi_name}_p05"] = stats["p05"]
                flat[f"{roi_name}_p95"] = stats["p95"]
        flattened_rows.append(flat)

    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flattened_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量应用ROI模板到多个矩阵并导出汇总表")
    parser.add_argument("--template-json", required=True, help="ROI模板JSON路径")
    parser.add_argument("--matrix-dir", required=True, help="矩阵CSV所在目录")
    parser.add_argument("--matrix-pattern", default="*.csv", help="矩阵CSV文件名模式")
    parser.add_argument("--out-summary", required=True, help="输出汇总表CSV路径")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    template_json = Path(args.template_json)
    matrix_dir = Path(args.matrix_dir)
    out_summary = Path(args.out_summary)

    if not template_json.exists():
        raise FileNotFoundError(f"未找到模板JSON: {template_json}")
    if not matrix_dir.is_dir():
        raise FileNotFoundError(f"未找到矩阵目录: {matrix_dir}")

    # Load template
    roi_polygons = load_template(template_json)
    print(f"[INFO] 已加载ROI模板: {len(roi_polygons)}个ROI")
    print(f"       {[p['name'] for p in roi_polygons]}")

    # Find all matrix CSVs
    csv_files = find_matrix_csvs(matrix_dir, args.matrix_pattern)
    if not csv_files:
        raise RuntimeError(f"在 {matrix_dir} 中未找到矩阵CSV文件")

    print(f"[INFO] 找到 {len(csv_files)} 个矩阵CSV文件")

    # Process each matrix
    summary_data: list[dict] = []
    for csv_file in csv_files:
        try:
            print(f"[PROCESS] {csv_file.name}...", end=" ", flush=True)
            matrix = np.loadtxt(csv_file, delimiter=",")
            if matrix.ndim != 2:
                print("SKIP (not 2D)")
                continue

            roi_stats = apply_template_to_matrix(matrix, roi_polygons)
            row = {"matrix_name": csv_file.name, **roi_stats}
            summary_data.append(row)
            print(f"OK ({len(roi_stats)} ROI)")
        except Exception as e:
            print(f"ERROR: {e}")

    if not summary_data:
        raise RuntimeError("没有成功处理的矩阵。")

    # Export summary
    export_summary(summary_data, out_summary)
    print(f"[DONE] 汇总表已导出: {out_summary}")
    print(f"       共处理 {len(summary_data)} 个矩阵")


if __name__ == "__main__":
    main()
