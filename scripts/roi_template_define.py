#!/usr/bin/env python3
"""
Define ROI template interactively and save as JSON.

Usage:
python3 scripts/roi_template_define.py \
  --matrix-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1.csv \
  --out-json data/35/2/roi_template.json \
  --vmin 28 --vmax 40
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np


class RoiTemplateDefiner:
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
        self.ax.set_title("定义ROI模板: 左键加点, 右键撤销, n确认ROI, c清空, q保存并退出")
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
        self.ax.plot(poly_x, poly_y, "-", linewidth=1.5, color="lime")
        self.ax.text(vertices[0][0], vertices[0][1], roi_name, fontsize=8, color="white",
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.5))

        self.current_vertices.clear()
        self.redraw()
        print(f"[INFO] 已保存ROI: {roi_name}")

    def run(self) -> list[dict]:
        plt.show()
        return self.saved_polygons if self.export_requested else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="交互定义ROI模板并保存为JSON")
    parser.add_argument("--matrix-csv", required=True, help="参考温度矩阵CSV路径")
    parser.add_argument("--out-json", required=True, help="输出模板JSON路径")
    parser.add_argument("--vmin", type=float, default=None, help="显示热图最小温标")
    parser.add_argument("--vmax", type=float, default=None, help="显示热图最大温标")
    parser.add_argument("--cmap", default="inferno", help="热图配色，默认 inferno")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_csv = Path(args.matrix_csv)
    if not matrix_csv.exists():
        raise FileNotFoundError(f"未找到CSV: {matrix_csv}")

    out_json = Path(args.out_json)
    matrix = np.loadtxt(matrix_csv, delimiter=",")
    if matrix.ndim != 2:
        raise ValueError(f"CSV不是二维矩阵: shape={matrix.shape}")

    definer = RoiTemplateDefiner(matrix=matrix, vmin=args.vmin, vmax=args.vmax, cmap=args.cmap)
    polygons = definer.run()

    if not polygons:
        print("[INFO] 未保存（可能直接关闭窗口或未按 q）。")
        return

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(polygons, f, indent=2, ensure_ascii=False)

    print(f"[DONE] ROI模板已保存: {out_json}")
    print(f"       共 {len(polygons)} 个ROI: {[p['name'] for p in polygons]}")


if __name__ == "__main__":
    main()
