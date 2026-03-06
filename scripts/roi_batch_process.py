#!/usr/bin/env python3
"""
批量处理热成像数据 - 1张→100张自动化

支持：
- 递归扫描目录下所有CSV文件
- 并行处理 (多进程)
- 统一汇总报告生成
- 性能监控
- 详细日志记录
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Generator

import numpy as np
from functools import partial

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from roi_mediapipe_dynamic import (
    detect_landmarks, build_dynamic_rois, to_rgb, calc_stats
)


@dataclass
class ProcessResult:
    """处理结果"""
    input_file: Path
    status: str  # 'success' / 'error'
    output_csv: Path | None = None
    output_overlay: Path | None = None
    num_parts: int = 0  # 检测到的部位数
    error_msg: str | None = None
    process_time: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "input_file": str(self.input_file),
            "status": self.status,
            "output_csv": str(self.output_csv) if self.output_csv else "N/A",
            "output_overlay": str(self.output_overlay) if self.output_overlay else "N/A",
            "num_parts": self.num_parts,
            "error": self.error_msg or "N/A",
            "time(s)": f"{self.process_time:.2f}"
        }


def setup_logger(name: str, log_file: Path) -> logging.Logger:
    """设置日志"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # 文件处理器
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    
    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # 格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


def is_raw_thermal_csv(csv_file: Path) -> bool:
    """检查CSV文件是否为原始温度矩阵（不是处理结果）
    
    原始温度矩阵：纯数字数据，无标题行
    处理结果：包含 'roi_name' 等文本列标题
    """
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if not first_line:
                return False
            
            # 检查第一行是否包含文本（roi_name、row等）
            # 如果包含逗号且任意字段不是数字，说明有标题行或文本数据
            fields = first_line.split(',')
            for field in fields:
                field = field.strip().strip('\ufeff')  # 移除BOM
                # 尝试转换为float - 如果失败，说明是文本字段（标题）
                try:
                    float(field)
                except ValueError:
                    return False  # 包含非数字字段，不是原始矩阵
            
            return True  # 第一行全是数字，是原始矩阵
    except Exception:
        return False


def find_csv_files(input_dir: Path) -> Generator[Path, None, None]:
    """递归查找所有原始温度矩阵CSV文件"""
    for csv_file in input_dir.rglob("*.csv"):
        if is_raw_thermal_csv(csv_file):
            yield csv_file


def process_single_file(csv_file: Path, input_dir: Path, output_dir: Path, vmin: float, vmax: float, 
                       cmap: str, logger: logging.Logger) -> ProcessResult:
    """处理单个文件"""
    start_time = time.time()
    result = ProcessResult(
        input_file=csv_file,
        status="processing",
        process_time=0.0
    )
    
    try:
        logger.info(f"处理: {csv_file.relative_to(input_dir)}")
        
        # 1. 加载温度矩阵
        matrix = np.loadtxt(csv_file, delimiter=",")
        if matrix.ndim != 2:
            raise ValueError(f"不是二维矩阵: shape={matrix.shape}")
        
        h, w = matrix.shape
        logger.debug(f"  矩阵尺寸: {h}x{w}")
        
        # 2. 关键点检测
        rgb = to_rgb(matrix, vmin, vmax, cmap)
        landmarks = detect_landmarks(rgb)
        logger.debug(f"  检测到 {len(landmarks)} 个关键点")
        
        # 3. ROI 构建
        rois = build_dynamic_rois(h, w, landmarks)
        logger.debug(f"  构建了 {len(rois)} 个 ROI")
        
        # 4. 温度统计
        rows: list[dict] = []
        for roi_name, mask in rois.items():
            values = matrix[mask]
            stats = calc_stats(values)
            rows.append({"roi_name": roi_name, **stats})
        
        # 5. 输出路径
        try:
            rel_path = csv_file.parent.relative_to(input_dir)
        except ValueError:
            # 如果无法计算相对路径，使用绝对路径
            rel_path = csv_file.parent.name
        output_subdir = output_dir / rel_path
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        # 输出CSV
        output_csv = output_subdir / f"{csv_file.stem}_roi.csv"
        fieldnames = ["roi_name", "count", "min", "max", "mean", "median", "std", "p05", "p95"]
        with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        logger.info(f"  ✓ CSV 已保存: {output_csv.name}")
        
        # 处理成功
        result.status = "success"
        result.output_csv = output_csv
        result.num_parts = len(rois)
        result.process_time = time.time() - start_time
        
        logger.info(f"  ✓ 完成 (耗时 {result.process_time:.2f}s)")
        
    except Exception as e:
        result.status = "error"
        result.error_msg = str(e)
        result.process_time = time.time() - start_time
        logger.error(f"  ✗ 失败: {e}")
    
    return result


def batch_process(input_dir: Path, output_dir: Path, num_workers: int, 
                 vmin: float, vmax: float, cmap: str, log_file: Path) -> tuple[list[ProcessResult], float]:
    """批量处理"""
    logger = setup_logger("batch", log_file)
    
    logger.info("=" * 70)
    logger.info("热成像批量处理系统")
    logger.info("=" * 70)
    logger.info(f"输入目录: {input_dir}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"工作进程: {num_workers}")
    logger.info(f"温度范围: {vmin}~{vmax}°C")
    
    # 扫描文件
    csv_files = list(find_csv_files(input_dir))
    logger.info(f"发现 {len(csv_files)} 个CSV文件")
    
    if not csv_files:
        logger.warning("未找到任何CSV文件!")
        return [], 0.0
    
    # 排序便于追踪
    csv_files.sort()
    
    # 显示计划
    logger.info("\n" + "=" * 70)
    logger.info("处理计划:")
    logger.info("=" * 70)
    for i, f in enumerate(csv_files[:5], 1):
        logger.info(f"  {i}. {f.relative_to(input_dir)}")
    if len(csv_files) > 5:
        logger.info(f"  ... 及其他 {len(csv_files) - 5} 个文件")
    
    # 并行处理
    logger.info("\n" + "=" * 70)
    logger.info("开始处理...")
    logger.info("=" * 70 + "\n")
    
    start_time = time.time()
    
    process_func = partial(
        process_single_file,
        input_dir=input_dir,
        output_dir=output_dir,
        vmin=vmin,
        vmax=vmax,
        cmap=cmap,
        logger=logger
    )
    
    with Pool(num_workers) as pool:
        results = pool.map(process_func, csv_files)
    
    total_time = time.time() - start_time
    
    return results, total_time


def generate_summary_report(results: list[ProcessResult], output_dir: Path, 
                           total_time: float, logger: logging.Logger):
    """生成汇总报告"""
    
    logger.info("\n" + "=" * 70)
    logger.info("生成汇总报告...")
    logger.info("=" * 70)
    
    # 统计
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "error")
    avg_time = total_time / total if total > 0 else 0
    
    # 生成汇总CSV
    summary_csv = output_dir / "_batch_summary.csv"
    summary_rows = [r.to_dict() for r in results]
    
    if summary_rows:
        with summary_csv.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
            writer.writeheader()
            writer.writerows(summary_rows)
    
    logger.info(f"\n汇总报告已保存: {summary_csv}")
    
    # 生成统计报告
    stats_file = output_dir / "_batch_statistics.txt"
    with stats_file.open("w", encoding="utf-8-sig") as f:
        f.write("=" * 70 + "\n")
        f.write("热成像批量处理 - 统计报告\n")
        f.write("=" * 70 + "\n\n")
        
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("处理统计:\n")
        f.write(f"  总文件数:   {total}\n")
        f.write(f"  成功:       {success} ✓\n")
        f.write(f"  失败:       {failed} ✗\n")
        f.write(f"  成功率:     {success/total*100:.1f}%\n\n")
        
        f.write("性能统计:\n")
        f.write(f"  总耗时:     {total_time:.2f} 秒\n")
        f.write(f"  平均/文件:  {avg_time:.2f} 秒\n")
        f.write(f"  吞吐量:     {total/total_time:.1f} 文件/秒\n\n")
        
        if failed > 0:
            f.write("失败文件列表:\n")
            for r in results:
                if r.status == "error":
                    f.write(f"  - {r.input_file.name}: {r.error_msg}\n")
    
    logger.info(f"统计报告已保存: {stats_file}")
    
    # 屏幕输出摘要
    logger.info("\n" + "=" * 70)
    logger.info("处理完成！")
    logger.info("=" * 70)
    logger.info(f"✓ 成功: {success}/{total} ({success/total*100:.1f}%)")
    if failed > 0:
        logger.warning(f"✗ 失败: {failed}/{total}")
    logger.info(f"⏱️  总耗时: {total_time:.2f} 秒")
    logger.info(f"📊 吞吐量: {total/total_time:.1f} 文件/秒")
    logger.info(f"📁 输出目录: {output_dir}")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="批量处理热成像数据 (1张→100张自动化)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 批量处理当前目录下的所有CSV
  python roi_batch_process.py --input-dir data/patients --output-dir reports

  # 使用4个工作进程处理
  python roi_batch_process.py --input-dir data --output-dir output --num-workers 4

  # 自定义温度范围
  python roi_batch_process.py --input-dir data --output-dir output --vmin 25 --vmax 45
        """
    )
    parser.add_argument("--input-dir", required=True, type=Path,
                       help="输入目录（递归扫描所有CSV文件）")
    parser.add_argument("--output-dir", required=True, type=Path,
                       help="输出目录（保存CSV和日志）")
    parser.add_argument("--num-workers", type=int, default=None,
                       help=f"并行工作进程数 (默认: {cpu_count()})")
    parser.add_argument("--vmin", type=float, default=28,
                       help="温度下限 (默认: 28°C)")
    parser.add_argument("--vmax", type=float, default=40,
                       help="温度上限 (默认: 40°C)")
    parser.add_argument("--cmap", default="inferno",
                       help="热图配色 (默认: inferno)")
    
    args = parser.parse_args()
    
    # 参数验证
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    num_workers = args.num_workers or cpu_count()
    
    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        sys.exit(1)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 日志文件
    log_file = output_dir / f"batch_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # 执行批量处理
    results, total_time = batch_process(
        input_dir=input_dir,
        output_dir=output_dir,
        num_workers=num_workers,
        vmin=args.vmin,
        vmax=args.vmax,
        cmap=args.cmap,
        log_file=log_file
    )
    
    # 生成报告
    logger = logging.getLogger("batch")
    generate_summary_report(results, output_dir, total_time, logger)


if __name__ == "__main__":
    main()
