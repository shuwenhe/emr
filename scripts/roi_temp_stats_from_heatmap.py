#!/usr/bin/env python3
"""
Interactive ROI temperature statistics tool for thermal matrix CSV.

Usage example:
python3 scripts/roi_temp_stats_from_heatmap.py \
  --matrix-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1.csv \
  --out-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1_roi_stats.csv \
  --vmin 28 --vmax 40
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np


class RoiSelector:
    def __init__(self, matrix: np.ndarray, vmin: float | None, vmax: float | None, cmap: str) -> None:
        self.matrix = matrix
        self.height, self.width = matrix.shape
        self.vmin = vmin
        self.vmax = vmax
        self.cmap = cmap

        self.current_vertices: list[tuple[float, float]] = []
        self.saved_polygons: list[dict] = []

        self.fig, self.ax = plt.subplots(figsize=(8, 10))
        self.im = self.ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
        self.fig.colorbar(self.im, ax=self.ax, label="Temperature (°C)")
        self.ax.set_title("ROI标注: 左键加点, 右键撤销, n确认ROI, c清空当前, q导出并退出")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")

        self.current_line, = self.ax.plot([], [], "-o", color="cyan", linewidth=1.5, markersize=4)

        self.cid_click = self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.cid_key = self.fig.canvas.mpl_connect("key_press_event", self.on_key)

        self.export_requested = False

    def redraw(self) -> None:
        if self.current_vertices:
            xs = [p[0] for p in self.current_vertices]
            ys = [p[1] for p in self.current_vertices]
            self.current_line.set_data(xs, ys)
        else:
            self.current_line.set_data([], [])
        self.fig.canvas.draw_idle()

    def on_click(self, event) -> None:
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return

        x = float(np.clip(event.xdata, 0, self.width - 1))
        y = float(np.clip(event.ydata, 0, self.height - 1))

        if event.button == 1:
            self.current_vertices.append((x, y))
        elif event.button == 3 and self.current_vertices:
            self.current_vertices.pop()
        self.redraw()

    def on_key(self, event) -> None:
        if event.key == "c":
            self.current_vertices.clear()
            self.redraw()
            print("[INFO] 已清空当前ROI。")
        elif event.key == "n":
            self.finalize_current_polygon()
        elif event.key == "q":
            self.export_requested = True
            plt.close(self.fig)

    def finalize_current_polygon(self) -> None:
        if len(self.current_vertices) < 3:
            print("[WARN] 至少需要3个点才能形成多边形ROI。")
            return

        roi_name = input("请输入ROI名称（如 forehead/chest/left_arm）: ").strip()
        if not roi_name:
            roi_name = f"roi_{len(self.saved_polygons) + 1}"

        vertices = self.current_vertices.copy()
        self.saved_polygons.append({"name": roi_name, "vertices": vertices})

        poly_x = [p[0] for p in vertices] + [vertices[0][0]]
        poly_y = [p[1] for p in vertices] + [vertices[0][1]]
        self.ax.plot(poly_x, poly_y, "-", linewidth=1.5)
        self.ax.text(vertices[0][0], vertices[0][1], roi_name, fontsize=8, color="white")

        self.current_vertices.clear()
        self.redraw()
        print(f"[INFO] 已保存ROI: {roi_name}")

    def run(self) -> list[dict]:
        plt.show()
        return self.saved_polygons if self.export_requested else []


def polygon_mask(height: int, width: int, vertices: list[tuple[float, float]]) -> np.ndarray:
    path = MplPath(vertices)
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    points = np.vstack((xx.ravel(), yy.ravel())).T
    mask = path.contains_points(points, radius=0.5)
    return mask.reshape((height, width))


def calc_stats(values: np.ndarray) -> dict[str, float]:
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


def export_stats(matrix: np.ndarray, polygons: list[dict], out_csv: Path) -> None:
    rows: list[dict] = []
    h, w = matrix.shape

    for item in polygons:
        name = item["name"]
        vertices = item["vertices"]
        mask = polygon_mask(h, w, vertices)
        values = matrix[mask]

        if values.size == 0:
            print(f"[WARN] ROI '{name}' 没有覆盖到有效像素，已跳过。")
            continue

        stats = calc_stats(values)
        row = {"roi_name": name, **stats}
        rows.append(row)

    if not rows:
        raise RuntimeError("没有可导出的ROI统计结果。")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["roi_name", "count", "min", "max", "mean", "median", "std", "p05", "p95"]
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="在热图上点选ROI并导出温度统计CSV")
    parser.add_argument("--matrix-csv", required=True, help="温度矩阵CSV路径")
    parser.add_argument("--out-csv", help="输出统计CSV路径，默认在输入CSV旁边生成 *_roi_stats.csv")
    parser.add_argument("--vmin", type=float, default=None, help="显示热图最小温标")
    parser.add_argument("--vmax", type=float, default=None, help="显示热图最大温标")
    parser.add_argument("--cmap", default="inferno", help="热图配色，默认 inferno")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_csv = Path(args.matrix_csv)
    if not matrix_csv.exists():
        raise FileNotFoundError(f"未找到CSV: {matrix_csv}")

    out_csv = Path(args.out_csv) if args.out_csv else matrix_csv.with_name(f"{matrix_csv.stem}_roi_stats.csv")

    matrix = np.loadtxt(matrix_csv, delimiter=",")
    if matrix.ndim != 2:
        raise ValueError(f"CSV不是二维矩阵: shape={matrix.shape}")

    selector = RoiSelector(matrix=matrix, vmin=args.vmin, vmax=args.vmax, cmap=args.cmap)
    polygons = selector.run()

    if not polygons:
        print("[INFO] 未导出（可能直接关闭窗口或未按 q）。")
        return

    export_stats(matrix, polygons, out_csv)
    print(f"[DONE] ROI统计已导出: {out_csv}")


if __name__ == "__main__":
    main()
