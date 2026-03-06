#!/usr/bin/env python3
"""
Use MediaPipe Pose landmarks to dynamically define body-part ROI on thermal matrix,
then export temperature statistics.

Usage:
python3 scripts/roi_mediapipe_dynamic.py \
  --matrix-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1.csv \
  --out-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1_mediapipe_roi.csv \
  --out-overlay data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1_mediapipe_overlay.png \
  --vmin 28 --vmax 40
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath


@dataclass
class Pt:
    x: float
    y: float


def rect_mask(height: int, width: int, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    x1i = int(np.clip(min(x1, x2), 0, width - 1))
    x2i = int(np.clip(max(x1, x2), 0, width - 1))
    y1i = int(np.clip(min(y1, y2), 0, height - 1))
    y2i = int(np.clip(max(y1, y2), 0, height - 1))
    mask[y1i : y2i + 1, x1i : x2i + 1] = True
    return mask


def polygon_mask(height: int, width: int, vertices: list[tuple[float, float]]) -> np.ndarray:
    path = MplPath(vertices)
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    points = np.vstack((xx.ravel(), yy.ravel())).T
    mask = path.contains_points(points, radius=0.5)
    return mask.reshape((height, width))


def segment_mask(height: int, width: int, p1: Pt, p2: Pt, thickness: float) -> np.ndarray:
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    px = xx.astype(np.float32)
    py = yy.astype(np.float32)

    x1, y1 = float(p1.x), float(p1.y)
    x2, y2 = float(p2.x), float(p2.y)

    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy

    if denom < 1e-6:
        dist2 = (px - x1) ** 2 + (py - y1) ** 2
        return dist2 <= thickness * thickness

    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = np.clip(t, 0.0, 1.0)

    proj_x = x1 + t * dx
    proj_y = y1 + t * dy

    dist2 = (px - proj_x) ** 2 + (py - proj_y) ** 2
    return dist2 <= thickness * thickness


def calc_stats(values: np.ndarray) -> dict[str, float]:
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


def to_rgb(matrix: np.ndarray, vmin: float | None, vmax: float | None, cmap_name: str) -> np.ndarray:
    lo = float(np.min(matrix)) if vmin is None else float(vmin)
    hi = float(np.max(matrix)) if vmax is None else float(vmax)
    if hi <= lo:
        hi = lo + 1e-6
    norm = (matrix - lo) / (hi - lo)
    norm = np.clip(norm, 0.0, 1.0)

    cmap = plt.get_cmap(cmap_name)
    rgba = cmap(norm)
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    return rgb


def detect_landmarks(rgb: np.ndarray) -> dict[str, Pt]:
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError("未安装 mediapipe，请先执行: pip install mediapipe") from exc

    h, w, _ = rgb.shape
    mp_pose = mp.solutions.pose

    with mp_pose.Pose(
        static_image_mode=True,
        model_complexity=2,
        smooth_landmarks=False,
        enable_segmentation=False,
        min_detection_confidence=0.5,
    ) as pose:
        results = pose.process(rgb)

    if results.pose_landmarks is None:
        raise RuntimeError("MediaPipe 未检测到人体关键点。请确认图像包含清晰人体轮廓。")

    lm = results.pose_landmarks.landmark

    def p(idx: int) -> Pt:
        return Pt(
            x=float(np.clip(lm[idx].x * w, 0, w - 1)),
            y=float(np.clip(lm[idx].y * h, 0, h - 1)),
        )

    landmarks = {
        "nose": p(0),
        "left_eye": p(2),
        "right_eye": p(5),
        "mouth_left": p(9),
        "mouth_right": p(10),
        "left_shoulder": p(11),
        "right_shoulder": p(12),
        "left_elbow": p(13),
        "right_elbow": p(14),
        "left_wrist": p(15),
        "right_wrist": p(16),
        "left_hip": p(23),
        "right_hip": p(24),
        "left_knee": p(25),
        "right_knee": p(26),
        "left_ankle": p(27),
        "right_ankle": p(28),
    }
    return landmarks


def dist(a: Pt, b: Pt) -> float:
    return float(np.hypot(a.x - b.x, a.y - b.y))


def build_dynamic_rois(height: int, width: int, lm: dict[str, Pt]) -> dict[str, np.ndarray]:
    ls = lm["left_shoulder"]
    rs = lm["right_shoulder"]
    le = lm["left_elbow"]
    re = lm["right_elbow"]
    lw = lm["left_wrist"]
    rw = lm["right_wrist"]
    lh = lm["left_hip"]
    rh = lm["right_hip"]
    lk = lm["left_knee"]
    rk = lm["right_knee"]
    la = lm["left_ankle"]
    ra = lm["right_ankle"]
    nose = lm["nose"]
    ley = lm["left_eye"]
    rey = lm["right_eye"]
    ml = lm["mouth_left"]
    mr = lm["mouth_right"]

    shoulder_w = max(20.0, dist(ls, rs))
    head_r = max(6.0, shoulder_w * 0.18)
    arm_t = max(4.0, shoulder_w * 0.10)
    leg_t = max(5.0, shoulder_w * 0.12)

    eye_mid = Pt((ley.x + rey.x) / 2.0, (ley.y + rey.y) / 2.0)
    mouth_mid = Pt((ml.x + mr.x) / 2.0, (ml.y + mr.y) / 2.0)

    rois: dict[str, np.ndarray] = {}

    rois["额头"] = rect_mask(
        height,
        width,
        eye_mid.x - 0.9 * head_r,
        eye_mid.y - 1.2 * head_r,
        eye_mid.x + 0.9 * head_r,
        eye_mid.y - 0.1 * head_r,
    )

    rois["左眼"] = rect_mask(height, width, ley.x - 0.5 * head_r, ley.y - 0.35 * head_r, ley.x + 0.5 * head_r, ley.y + 0.35 * head_r)
    rois["右眼"] = rect_mask(height, width, rey.x - 0.5 * head_r, rey.y - 0.35 * head_r, rey.x + 0.5 * head_r, rey.y + 0.35 * head_r)

    left_cheek_c = Pt((ley.x + ml.x) / 2.0, (ley.y + ml.y) / 2.0)
    right_cheek_c = Pt((rey.x + mr.x) / 2.0, (rey.y + mr.y) / 2.0)
    rois["左脸颊"] = rect_mask(height, width, left_cheek_c.x - 0.55 * head_r, left_cheek_c.y - 0.45 * head_r, left_cheek_c.x + 0.55 * head_r, left_cheek_c.y + 0.45 * head_r)
    rois["右脸颊"] = rect_mask(height, width, right_cheek_c.x - 0.55 * head_r, right_cheek_c.y - 0.45 * head_r, right_cheek_c.x + 0.55 * head_r, right_cheek_c.y + 0.45 * head_r)

    rois["鼻子"] = rect_mask(height, width, nose.x - 0.35 * head_r, nose.y - 0.35 * head_r, nose.x + 0.35 * head_r, nose.y + 0.35 * head_r)

    rois["下巴"] = rect_mask(height, width, mouth_mid.x - 0.9 * head_r, mouth_mid.y + 0.2 * head_r, mouth_mid.x + 0.9 * head_r, mouth_mid.y + 1.0 * head_r)

    neck_top = min(ls.y, rs.y) - 0.05 * head_r
    neck_bottom = min(ls.y, rs.y) + 0.75 * head_r
    rois["颈部"] = rect_mask(height, width, min(ls.x, rs.x) + 0.25 * shoulder_w, neck_top, max(ls.x, rs.x) - 0.25 * shoulder_w, neck_bottom)

    rois["胸部"] = polygon_mask(
        height,
        width,
        [
            (ls.x, ls.y),
            (rs.x, rs.y),
            (rh.x, rh.y - 0.45 * (rh.y - rs.y)),
            (lh.x, lh.y - 0.45 * (lh.y - ls.y)),
        ],
    )

    rois["腹部"] = polygon_mask(
        height,
        width,
        [
            (lh.x + 0.1 * shoulder_w, lh.y - 0.15 * head_r),
            (rh.x - 0.1 * shoulder_w, rh.y - 0.15 * head_r),
            (rh.x - 0.05 * shoulder_w, rh.y + 0.55 * head_r),
            (lh.x + 0.05 * shoulder_w, lh.y + 0.55 * head_r),
        ],
    )

    rois["左臂"] = segment_mask(height, width, ls, le, arm_t) | segment_mask(height, width, le, lw, arm_t)
    rois["右臂"] = segment_mask(height, width, rs, re, arm_t) | segment_mask(height, width, re, rw, arm_t)
    rois["左腿"] = segment_mask(height, width, lh, lk, leg_t) | segment_mask(height, width, lk, la, leg_t)
    rois["右腿"] = segment_mask(height, width, rh, rk, leg_t) | segment_mask(height, width, rk, ra, leg_t)

    return rois


def save_overlay(matrix: np.ndarray, rois: dict[str, np.ndarray], landmarks: dict[str, Pt], out_path: Path, vmin: float | None, vmax: float | None, cmap: str) -> None:
    h, w = matrix.shape
    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=180)
    ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")

    colors = ["cyan", "lime", "yellow", "magenta", "orange", "white", "red", "deepskyblue"]

    for idx, (name, mask) in enumerate(rois.items()):
        ys, xs = np.where(mask)
        if xs.size == 0:
            continue
        color = colors[idx % len(colors)]
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        rect = plt.Rectangle((x_min, y_min), x_max - x_min + 1, y_max - y_min + 1, fill=False, edgecolor=color, linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x_min, max(0, y_min - 4), name, color=color, fontsize=7, weight="bold")

    for key, pt in landmarks.items():
        ax.scatter([pt.x], [pt.y], s=8, c="white")

    ax.set_axis_off()
    plt.tight_layout(pad=0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MediaPipe关键点动态ROI温度统计")
    parser.add_argument("--matrix-csv", required=True, help="温度矩阵CSV路径")
    parser.add_argument("--out-csv", help="输出统计CSV路径，默认 *_mediapipe_roi.csv")
    parser.add_argument("--out-overlay", help="输出ROI叠加图路径，默认 *_mediapipe_overlay.png")
    parser.add_argument("--vmin", type=float, default=None, help="可视化最小温标")
    parser.add_argument("--vmax", type=float, default=None, help="可视化最大温标")
    parser.add_argument("--cmap", default="inferno", help="热图配色")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_csv = Path(args.matrix_csv)
    if not matrix_csv.exists():
        raise FileNotFoundError(f"未找到CSV: {matrix_csv}")

    out_csv = Path(args.out_csv) if args.out_csv else matrix_csv.with_name(f"{matrix_csv.stem}_mediapipe_roi.csv")
    out_overlay = Path(args.out_overlay) if args.out_overlay else matrix_csv.with_name(f"{matrix_csv.stem}_mediapipe_overlay.png")

    matrix = np.loadtxt(matrix_csv, delimiter=",")
    if matrix.ndim != 2:
        raise ValueError(f"CSV不是二维矩阵: shape={matrix.shape}")

    h, w = matrix.shape
    print(f"[INFO] 矩阵尺寸: {h} x {w}")

    rgb = to_rgb(matrix, args.vmin, args.vmax, args.cmap)
    landmarks = detect_landmarks(rgb)
    rois = build_dynamic_rois(h, w, landmarks)

    rows: list[dict] = []
    for roi_name, mask in rois.items():
        values = matrix[mask]
        stats = calc_stats(values)
        rows.append({"roi_name": roi_name, **stats})
        print(
            f"  ✓ {roi_name:8s} count={stats['count']:5d} "
            f"mean={stats['mean']:6.2f}°C (min={stats['min']:5.2f}, max={stats['max']:5.2f}, std={stats['std']:5.2f})"
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["roi_name", "count", "min", "max", "mean", "median", "std", "p05", "p95"]
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    save_overlay(matrix, rois, landmarks, out_overlay, args.vmin, args.vmax, args.cmap)

    print(f"\n[DONE] ROI统计已导出: {out_csv}")
    print(f"[DONE] ROI叠加图已导出: {out_overlay}")


if __name__ == "__main__":
    main()
