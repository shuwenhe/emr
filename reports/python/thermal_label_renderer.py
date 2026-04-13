from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

THERMAL_PLOT_BOUNDS = {
    "left": 3,
    "right": 72,
    "top": 8,
    "bottom": 97,
}

_CJK_FONT_CANDIDATES = [
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Heiti SC",
    "Arial Unicode MS",
]

_CJK_FONT_PROP: Optional[fm.FontProperties] = None
_FACIAL_LABEL_OFFSETS = {
    "右眼": (8.0, -4.0),
    "左眼": (-8.0, -4.0),
    "鼻子": (0.0, -1.8),
    "右脸颊": (11.0, 1.5),
    "左脸颊": (-11.0, 1.5),
    "额头": (0.0, -7.5),
    "口部": (0.0, 4.0),
    "下巴": (0.0, 7.0),
    "颈部": (0.0, 8.0),
}

_HEAD_LABEL_KEYWORDS = (
    "额",
    "眼",
    "鼻",
    "口",
    "脸",
    "颊",
    "下巴",
    "颈",
    "头",
)


def _get_cjk_font_prop() -> Optional[fm.FontProperties]:
    global _CJK_FONT_PROP
    if _CJK_FONT_PROP is not None:
        return _CJK_FONT_PROP

    try:
        for entry in fm.fontManager.ttflist:
            if entry.name in _CJK_FONT_CANDIDATES:
                _CJK_FONT_PROP = fm.FontProperties(fname=entry.fname)
                return _CJK_FONT_PROP

        for font_path in fm.findSystemFonts():
            lowered = font_path.lower()
            if (
                "notosanscjk" in lowered
                or "sourcehansans" in lowered
                or "wqy-zenhei" in lowered
                or "wqy-microhei" in lowered
                or "simhei" in lowered
                or "msyh" in lowered
                or "yahei" in lowered
                or "pingfang" in lowered
                or "heiti" in lowered
            ):
                _CJK_FONT_PROP = fm.FontProperties(fname=font_path)
                return _CJK_FONT_PROP
    except Exception:
        return None

    return None


def build_roi_label_points(report: Dict[str, Any]) -> list[Dict[str, Any]]:
    analysis = report.get("analysis") if isinstance(report, dict) else None
    if not isinstance(analysis, dict):
        return []
    roi_analysis = analysis.get("roi_analysis")
    if not isinstance(roi_analysis, dict):
        return []
    roi_list = roi_analysis.get("roi_list")
    if not isinstance(roi_list, list):
        return []

    points: list[Dict[str, Any]] = []
    for item in roi_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            mean_c = float(item.get("mean_c"))
        except Exception:
            continue

        center_x = item.get("center_x_pct")
        center_y = item.get("center_y_pct")
        if center_x is None or center_y is None:
            continue
        try:
            cx = max(0.0, min(100.0, float(center_x)))
            cy = max(0.0, min(100.0, float(center_y)))
        except Exception:
            continue

        x = THERMAL_PLOT_BOUNDS["left"] + (cx / 100.0) * (
            THERMAL_PLOT_BOUNDS["right"] - THERMAL_PLOT_BOUNDS["left"]
        )
        y = THERMAL_PLOT_BOUNDS["top"] + (cy / 100.0) * (
            THERMAL_PLOT_BOUNDS["bottom"] - THERMAL_PLOT_BOUNDS["top"]
        )
        label_x = x
        label_y = y

        for key, (dx, dy) in _FACIAL_LABEL_OFFSETS.items():
            if key in name:
                label_x = max(2.0, min(98.0, x + dx))
                label_y = max(2.0, min(98.0, y + dy))
                break

        points.append(
            {
                "name": name,
                "mean_c": mean_c,
                "x": x,
                "y": y,
                "label_x": label_x,
                "label_y": label_y,
            }
        )

    points.sort(key=lambda p: (p["label_y"], p["label_x"]))
    min_y_gap = 3.2
    for i in range(1, len(points)):
        prev = points[i - 1]
        cur = points[i]
        if abs(cur["label_x"] - prev["label_x"]) < 8 and (cur["label_y"] - prev["label_y"]) < min_y_gap:
            cur["label_y"] = min(97.0, prev["label_y"] + min_y_gap)

    for i in range(1, len(points)):
        prev = points[i - 1]
        cur = points[i]
        is_head_pair = any(keyword in cur["name"] for keyword in _HEAD_LABEL_KEYWORDS) or any(
            keyword in prev["name"] for keyword in _HEAD_LABEL_KEYWORDS
        )
        if not is_head_pair:
            continue
        if abs(cur["label_x"] - prev["label_x"]) < 12 and (cur["label_y"] - prev["label_y"]) < 4.2:
            cur["label_y"] = min(97.0, prev["label_y"] + 4.2)

    return points


def render_labeled_thermal_image(
    base_image: Path,
    report: Dict[str, Any],
    suffix: str,
    out_path: Optional[Path] = None,
) -> Optional[Path]:
    points = build_roi_label_points(report)
    if not points:
        return base_image

    try:
        cjk_font = _get_cjk_font_prop()
        image = plt.imread(str(base_image))
        fig, ax = plt.subplots(figsize=(6, 4), dpi=180)
        ax.imshow(image)
        ax.axis("off")

        h, w = image.shape[0], image.shape[1]

        for point in points:
            px = (point["x"] / 100.0) * w
            py = (point["y"] / 100.0) * h
            lpx = (point.get("label_x", point["x"]) / 100.0) * w
            lpy = (point.get("label_y", point["y"]) / 100.0) * h
            text = f"{point['name']} {point['mean_c']:.1f}°C"
            ax.annotate(
                text,
                xy=(px, py),
                xytext=(lpx, lpy),
                textcoords="data",
                fontsize=4,
                fontproperties=cjk_font,
                color="white",
                ha="center",
                va="center",
                arrowprops={
                    "arrowstyle": "-",
                    "color": "#0f172a",
                    "lw": 0.5,
                    "alpha": 0.85,
                },
                bbox={
                    "boxstyle": "round,pad=0.18",
                    "facecolor": "#0f172a",
                    "alpha": 0.72,
                    "edgecolor": "#ffffff",
                    "linewidth": 0.4,
                },
            )

        target_path = out_path or base_image.with_name(f"{base_image.stem}_{suffix}{base_image.suffix}")
        fig.savefig(str(target_path), bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        if target_path.exists() and target_path.is_file():
            return target_path
        return base_image
    except Exception as exc:
        logging.debug("render labeled thermal image failed: %s", exc)
        return base_image
