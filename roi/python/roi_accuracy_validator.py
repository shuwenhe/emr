#!/usr/bin/env python3
"""
ROI 掩码准确度验证工具

提供多种方法评估姿态识别生成的掩码质量：
1. 可视化检查 - 生成详细的掩码叠加图
2. 关键点置信度 - 检查MediaPipe检测质量
3. 覆盖率分析 - 检查ROI是否覆盖合理
4. 温度合理性 - 检查各部位温度是否符合生理规律
5. 掩码重叠检测 - 检查ROI之间的重叠情况
"""

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from dataclasses import dataclass
import csv


@dataclass
class Pt:
    x: float
    y: float


def load_matrix(csv_path: Path) -> np.ndarray:
    """加载温度矩阵"""
    matrix = np.loadtxt(csv_path, delimiter=",")
    if matrix.ndim != 2:
        raise ValueError(f"CSV不是二维矩阵: shape={matrix.shape}")
    return matrix


def to_rgb(matrix: np.ndarray, vmin: float | None, vmax: float | None, cmap_name: str) -> np.ndarray:
    """温度矩阵转RGB"""
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


def detect_landmarks_with_confidence(rgb: np.ndarray) -> tuple[dict[str, Pt], dict[str, float]]:
    """检测关键点并返回置信度"""
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError("未安装 mediapipe") from exc

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
        raise RuntimeError("MediaPipe 未检测到人体关键点")

    lm = results.pose_landmarks.landmark

    def p(idx: int) -> Pt:
        return Pt(
            x=float(np.clip(lm[idx].x * w, 0, w - 1)),
            y=float(np.clip(lm[idx].y * h, 0, h - 1)),
        )

    def conf(idx: int) -> float:
        return float(lm[idx].visibility)

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

    confidences = {
        "nose": conf(0),
        "left_eye": conf(2),
        "right_eye": conf(5),
        "mouth_left": conf(9),
        "mouth_right": conf(10),
        "left_shoulder": conf(11),
        "right_shoulder": conf(12),
        "left_elbow": conf(13),
        "right_elbow": conf(14),
        "left_wrist": conf(15),
        "right_wrist": conf(16),
        "left_hip": conf(23),
        "right_hip": conf(24),
        "left_knee": conf(25),
        "right_knee": conf(26),
        "left_ankle": conf(27),
        "right_ankle": conf(28),
    }

    return landmarks, confidences


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


def dist(a: Pt, b: Pt) -> float:
    return float(np.hypot(a.x - b.x, a.y - b.y))


def build_dynamic_rois(height: int, width: int, lm: dict[str, Pt]) -> dict[str, np.ndarray]:
    """构建动态ROI（与主脚本相同）"""
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

    rois["额头"] = rect_mask(height, width, eye_mid.x - 0.9 * head_r, eye_mid.y - 1.2 * head_r, eye_mid.x + 0.9 * head_r, eye_mid.y - 0.1 * head_r)
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

    rois["胸部"] = polygon_mask(height, width, [(ls.x, ls.y), (rs.x, rs.y), (rh.x, rh.y - 0.45 * (rh.y - rs.y)), (lh.x, lh.y - 0.45 * (lh.y - ls.y))])
    rois["腹部"] = polygon_mask(height, width, [(lh.x + 0.1 * shoulder_w, lh.y - 0.15 * head_r), (rh.x - 0.1 * shoulder_w, rh.y - 0.15 * head_r), (rh.x - 0.05 * shoulder_w, rh.y + 0.55 * head_r), (lh.x + 0.05 * shoulder_w, lh.y + 0.55 * head_r)])

    rois["左臂"] = segment_mask(height, width, ls, le, arm_t) | segment_mask(height, width, le, lw, arm_t)
    rois["右臂"] = segment_mask(height, width, rs, re, arm_t) | segment_mask(height, width, re, rw, arm_t)
    rois["左腿"] = segment_mask(height, width, lh, lk, leg_t) | segment_mask(height, width, lk, la, leg_t)
    rois["右腿"] = segment_mask(height, width, rh, rk, leg_t) | segment_mask(height, width, rk, ra, leg_t)

    return rois


def validate_keypoint_confidence(confidences: dict[str, float]) -> dict:
    """验证关键点置信度"""
    print("\n" + "=" * 60)
    print("【验证1】关键点置信度检查")
    print("=" * 60)
    
    low_conf_threshold = 0.5
    medium_conf_threshold = 0.7
    
    low_conf_points = []
    medium_conf_points = []
    high_conf_points = []
    
    for name, conf in confidences.items():
        if conf < low_conf_threshold:
            status = "❌ 低"
            low_conf_points.append(name)
        elif conf < medium_conf_threshold:
            status = "⚠️  中"
            medium_conf_points.append(name)
        else:
            status = "✓ 高"
            high_conf_points.append(name)
        print(f"  {name:15s}: {conf:.3f} {status}")
    
    avg_conf = np.mean(list(confidences.values()))
    min_conf = np.min(list(confidences.values()))
    
    print(f"\n  平均置信度: {avg_conf:.3f}")
    print(f"  最低置信度: {min_conf:.3f}")
    
    if low_conf_points:
        print(f"\n  ⚠️  警告：{len(low_conf_points)} 个关键点置信度过低:")
        print(f"     {', '.join(low_conf_points)}")
        print(f"     这些关键点可能定位不准，影响相关ROI准确度")
    
    quality_score = avg_conf * 100
    print(f"\n  关键点质量评分: {quality_score:.1f}/100")
    
    return {
        "avg_confidence": avg_conf,
        "min_confidence": min_conf,
        "low_conf_count": len(low_conf_points),
        "quality_score": quality_score
    }


def validate_coverage(rois: dict[str, np.ndarray], h: int, w: int) -> dict:
    """验证ROI覆盖率"""
    print("\n" + "=" * 60)
    print("【验证2】ROI 覆盖率分析")
    print("=" * 60)
    
    total_pixels = h * w
    
    for name, mask in rois.items():
        count = np.sum(mask)
        coverage = count / total_pixels * 100
        print(f"  {name:8s}: {count:6d} 像素 ({coverage:5.2f}%)")
    
    # 总覆盖率（包含重叠）
    any_roi = np.zeros((h, w), dtype=bool)
    for mask in rois.values():
        any_roi |= mask
    
    total_covered = np.sum(any_roi)
    total_coverage = total_covered / total_pixels * 100
    
    print(f"\n  总覆盖率: {total_covered:6d} 像素 ({total_coverage:5.2f}%)")
    print(f"  未覆盖: {total_pixels - total_covered:6d} 像素 ({100 - total_coverage:5.2f}%)")
    
    return {
        "total_coverage": total_coverage,
        "covered_pixels": total_covered,
        "uncovered_pixels": total_pixels - total_covered
    }


def validate_overlap(rois: dict[str, np.ndarray]) -> dict:
    """检测ROI重叠情况"""
    print("\n" + "=" * 60)
    print("【验证3】ROI 重叠检测")
    print("=" * 60)
    
    roi_names = list(rois.keys())
    overlaps = []
    
    for i, name1 in enumerate(roi_names):
        for j, name2 in enumerate(roi_names):
            if i >= j:
                continue
            
            mask1 = rois[name1]
            mask2 = rois[name2]
            
            overlap = np.sum(mask1 & mask2)
            if overlap > 0:
                overlap_pct1 = overlap / np.sum(mask1) * 100
                overlap_pct2 = overlap / np.sum(mask2) * 100
                overlaps.append({
                    "roi1": name1,
                    "roi2": name2,
                    "pixels": overlap,
                    "pct1": overlap_pct1,
                    "pct2": overlap_pct2
                })
                
                if overlap_pct1 > 10 or overlap_pct2 > 10:
                    status = "⚠️  显著重叠"
                else:
                    status = "✓ 轻微重叠"
                
                print(f"  {name1} ∩ {name2}: {overlap} 像素 ({overlap_pct1:.1f}% / {overlap_pct2:.1f}%) {status}")
    
    if not overlaps:
        print("  ✓ 无ROI重叠")
    
    return {"overlaps": overlaps, "overlap_count": len(overlaps)}


def validate_temperature_reasonableness(matrix: np.ndarray, rois: dict[str, np.ndarray]) -> dict:
    """验证温度合理性"""
    print("\n" + "=" * 60)
    print("【验证4】温度合理性检查")
    print("=" * 60)
    
    # 正常体温范围（红外成像）
    normal_face_range = (35.5, 38.5)  # 面部
    normal_torso_range = (34.0, 38.5)  # 躯干
    normal_limb_range = (30.0, 37.0)   # 四肢
    
    face_parts = ["额头", "左眼", "右眼", "左脸颊", "右脸颊", "鼻子", "下巴"]
    torso_parts = ["颈部", "胸部", "腹部"]
    limb_parts = ["左臂", "右臂", "左腿", "右腿"]
    
    issues = []
    
    for roi_name, mask in rois.items():
        values = matrix[mask]
        if values.size == 0:
            print(f"  {roi_name:8s}: ❌ 无数据")
            issues.append(f"{roi_name}: 无数据")
            continue
        
        mean_temp = np.mean(values)
        min_temp = np.min(values)
        max_temp = np.max(values)
        std_temp = np.std(values)
        
        # 判断合理性
        if roi_name in face_parts:
            expected = normal_face_range
        elif roi_name in torso_parts:
            expected = normal_torso_range
        else:
            expected = normal_limb_range
        
        if expected[0] <= mean_temp <= expected[1]:
            status = "✓"
        elif mean_temp < expected[0] - 2 or mean_temp > expected[1] + 2:
            status = "❌ 异常"
            issues.append(f"{roi_name}: {mean_temp:.1f}°C 超出预期范围")
        else:
            status = "⚠️  边界"
        
        # 检查标准差（均匀性）
        if std_temp > 2.0:
            uniformity = "不均匀"
        elif std_temp > 1.0:
            uniformity = "一般"
        else:
            uniformity = "均匀"
        
        print(f"  {roi_name:8s}: {mean_temp:5.2f}°C (min={min_temp:5.2f}, max={max_temp:5.2f}, std={std_temp:4.2f}) {status} [{uniformity}]")
    
    if issues:
        print(f"\n  ⚠️  发现 {len(issues)} 个温度异常:")
        for issue in issues:
            print(f"     - {issue}")
    else:
        print("\n  ✓ 所有部位温度在合理范围内")
    
    return {"issues": issues, "issue_count": len(issues)}


def save_detailed_visualization(matrix: np.ndarray, rois: dict[str, np.ndarray], 
                               landmarks: dict[str, Pt], confidences: dict[str, float],
                               out_path: Path, vmin: float | None, vmax: float | None) -> None:
    """保存详细的可视化图"""
    h, w = matrix.shape
    
    fig = plt.figure(figsize=(20, 12))
    
    # 1. 原始热图
    ax1 = plt.subplot(2, 3, 1)
    im1 = ax1.imshow(matrix, cmap="inferno", vmin=vmin, vmax=vmax, origin="upper")
    ax1.set_title("原始温度矩阵", fontsize=14, weight="bold")
    plt.colorbar(im1, ax=ax1, label="温度 (°C)")
    ax1.axis("off")
    
    # 2. 关键点 + 置信度
    ax2 = plt.subplot(2, 3, 2)
    ax2.imshow(matrix, cmap="inferno", vmin=vmin, vmax=vmax, origin="upper")
    for name, pt in landmarks.items():
        conf = confidences[name]
        if conf > 0.7:
            color = "lime"
        elif conf > 0.5:
            color = "yellow"
        else:
            color = "red"
        ax2.scatter([pt.x], [pt.y], s=50, c=color, edgecolors="white", linewidths=1.5)
    ax2.set_title("关键点检测 (绿=高置信, 黄=中, 红=低)", fontsize=14, weight="bold")
    ax2.axis("off")
    
    # 3. ROI叠加
    ax3 = plt.subplot(2, 3, 3)
    ax3.imshow(matrix, cmap="inferno", vmin=vmin, vmax=vmax, origin="upper")
    colors = ["cyan", "lime", "yellow", "magenta", "orange", "white", "red", "deepskyblue"]
    for idx, (name, mask) in enumerate(rois.items()):
        ys, xs = np.where(mask)
        if xs.size == 0:
            continue
        color = colors[idx % len(colors)]
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        rect = plt.Rectangle((x_min, y_min), x_max - x_min + 1, y_max - y_min + 1,
                            fill=False, edgecolor=color, linewidth=1.5)
        ax3.add_patch(rect)
    ax3.set_title("ROI 边界框", fontsize=14, weight="bold")
    ax3.axis("off")
    
    # 4-6. 单独显示部分ROI掩码
    roi_list = list(rois.keys())
    for i in range(3):
        if i >= len(roi_list):
            break
        ax = plt.subplot(2, 3, 4 + i)
        roi_name = roi_list[i]
        mask = rois[roi_name]
        
        # 只显示mask区域的温度
        masked_temp = np.where(mask, matrix, np.nan)
        im = ax.imshow(masked_temp, cmap="inferno", vmin=vmin, vmax=vmax, origin="upper")
        ax.set_title(f"{roi_name} (像素={np.sum(mask)})", fontsize=12, weight="bold")
        plt.colorbar(im, ax=ax)
        ax.axis("off")
    
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n详细可视化已保存: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="ROI掩码准确度验证工具")
    parser.add_argument("--matrix-csv", required=True, help="温度矩阵CSV路径")
    parser.add_argument("--out-report", help="输出验证报告图像路径")
    parser.add_argument("--vmin", type=float, default=28, help="温度下限")
    parser.add_argument("--vmax", type=float, default=40, help="温度上限")
    args = parser.parse_args()
    
    matrix_csv = Path(args.matrix_csv)
    if not matrix_csv.exists():
        raise FileNotFoundError(f"未找到CSV: {matrix_csv}")
    
    out_report = Path(args.out_report) if args.out_report else matrix_csv.with_name(f"{matrix_csv.stem}_validation_report.png")
    
    print("=" * 60)
    print("ROI 掩码准确度验证")
    print("=" * 60)
    print(f"输入文件: {matrix_csv}")
    
    # 加载数据
    matrix = load_matrix(matrix_csv)
    h, w = matrix.shape
    print(f"矩阵尺寸: {h} x {w}")
    
    # 检测关键点
    rgb = to_rgb(matrix, args.vmin, args.vmax, "inferno")
    landmarks, confidences = detect_landmarks_with_confidence(rgb)
    
    # 构建ROI
    rois = build_dynamic_rois(h, w, landmarks)
    
    # 执行所有验证
    results = {}
    results["keypoint"] = validate_keypoint_confidence(confidences)
    results["coverage"] = validate_coverage(rois, h, w)
    results["overlap"] = validate_overlap(rois)
    results["temperature"] = validate_temperature_reasonableness(matrix, rois)
    
    # 生成详细可视化
    save_detailed_visualization(matrix, rois, landmarks, confidences, out_report, args.vmin, args.vmax)
    
    # 总结
    print("\n" + "=" * 60)
    print("【总体评估】")
    print("=" * 60)
    
    quality_score = results["keypoint"]["quality_score"]
    low_conf_count = results["keypoint"]["low_conf_count"]
    temp_issue_count = results["temperature"]["issue_count"]
    coverage = results["coverage"]["total_coverage"]
    
    print(f"  关键点质量: {quality_score:.1f}/100")
    print(f"  低置信度关键点: {low_conf_count} 个")
    print(f"  温度异常部位: {temp_issue_count} 个")
    print(f"  总覆盖率: {coverage:.2f}%")
    
    if quality_score > 80 and low_conf_count == 0 and temp_issue_count == 0:
        print("\n  ✅ 整体评估: 优秀 - ROI掩码准确度高")
    elif quality_score > 60 and temp_issue_count <= 2:
        print("\n  ✓ 整体评估: 良好 - ROI掩码基本准确")
    else:
        print("\n  ⚠️  整体评估: 需改进 - 建议检查图像质量或调整参数")
    
    print(f"\n验证完成！详细报告已保存至: {out_report}")
    print("=" * 60)


if __name__ == "__main__":
    main()
