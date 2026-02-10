"""设备接入服务的数据加载工具"""

import json
import csv
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, List

class ThermalDataLoader:
    """热成像数据加载器"""
    
    @staticmethod
    def load_metadata(dataset_path: str) -> Dict:
        """加载采集元数据"""
        metadata_file = Path(dataset_path) / "metadata.json"
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def load_thermal_data(dataset_path: str) -> np.ndarray:
        """加载热成像数据为二维数组"""
        thermal_file = Path(dataset_path) / "frame_0001.csv"
        
        with open(thermal_file, 'r') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        # 获取分辨率
        metadata = ThermalDataLoader.load_metadata(dataset_path)
        resolution = None
        if "capture" in metadata and metadata.get("capture"):
            resolution = metadata["capture"].get("resolution")
        if resolution is None:
            resolution = metadata.get("resolution")

        if isinstance(resolution, str) and "x" in resolution:
            cols_str, rows_str = resolution.lower().split("x", 1)
            cols, rows = int(cols_str), int(rows_str)
        else:
            cols, rows = resolution
        
        # 创建温度矩阵
        temp_matrix = np.zeros((rows, cols))
        for point in data:
            row = int(point['row'])
            col = int(point['col'])
            temp = float(point['temperature_c'])
            temp_matrix[row, col] = temp
        
        return temp_matrix
    
    @staticmethod
    def get_temperature_stats(dataset_path: str) -> Dict:
        """获取温度统计数据"""
        temp_matrix = ThermalDataLoader.load_thermal_data(dataset_path)
        
        return {
            "min": float(np.min(temp_matrix)),
            "max": float(np.max(temp_matrix)),
            "mean": float(np.mean(temp_matrix)),
            "std": float(np.std(temp_matrix)),
            "median": float(np.median(temp_matrix))
        }

def main():
    """演示如何加载和使用数据"""
    
    data_dir = Path(__file__).parent
    
    datasets = [
        "normal_face",
        "fever_face", 
        "hand_normal",
        "low_temp"
    ]
    
    print("=== 热成像数据加载演示 ===\n")
    
    for dataset_id in datasets:
        dataset_path = data_dir / dataset_id
        if not dataset_path.exists():
            print(f"⚠ 数据集 {dataset_id} 不存在")
            continue
        
        print(f"📊 数据集: {dataset_id}")
        
        # 加载元数据
        metadata = ThermalDataLoader.load_metadata(str(dataset_path))
        print(f"  设备型号: {metadata['device_model']}")
        print(f"  采集时间: {metadata['capture_time']}")
        print(f"  患者信息: {metadata['subject']}")
        
        # 加载热成像数据
        temp_matrix = ThermalDataLoader.load_thermal_data(str(dataset_path))
        print(f"  图像分辨率: {temp_matrix.shape}")
        
        # 获取统计数据
        stats = ThermalDataLoader.get_temperature_stats(str(dataset_path))
        print(f"  温度统计:")
        print(f"    最低: {stats['min']:.2f}°C")
        print(f"    最高: {stats['max']:.2f}°C")
        print(f"    平均: {stats['mean']:.2f}°C")
        print(f"    中位数: {stats['median']:.2f}°C")
        print(f"    标准差: {stats['std']:.2f}°C")
        
        print()

if __name__ == "__main__":
    main()
