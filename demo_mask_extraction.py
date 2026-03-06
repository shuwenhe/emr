#!/usr/bin/env python3
"""
演示掩码如何从温度矩阵中提取数据
"""
import numpy as np

print("=" * 60)
print("演示：掩码如何提取温度数据")
print("=" * 60)

# 1. 创建一个小的温度矩阵（模拟实际的384×288矩阵）
print("\n【步骤1】创建温度矩阵 (5×5)")
temperature_matrix = np.array([
    [35.2, 36.1, 37.8, 38.4, 36.5],
    [35.8, 36.5, 37.5, 38.2, 36.8],
    [36.2, 36.8, 37.2, 37.9, 37.1],
    [34.5, 35.9, 36.4, 37.3, 36.9],
    [34.1, 35.3, 35.8, 36.7, 36.2]
])
print("温度矩阵:")
print(temperature_matrix)
print(f"矩阵形状: {temperature_matrix.shape}")

# 2. 创建一个掩码（模拟额头区域）
print("\n【步骤2】创建掩码 (5×5 布尔数组)")
print("假设右上角是额头区域...")
forehead_mask = np.array([
    [False, False, True,  True,  False],
    [False, False, True,  True,  False],
    [False, False, False, False, False],
    [False, False, False, False, False],
    [False, False, False, False, False]
])
print("掩码 (True=额头, False=非额头):")
print(forehead_mask)

# 3. 关键操作：用掩码提取温度数据
print("\n【步骤3】关键操作：temperature_matrix[forehead_mask]")
print("=" * 60)
forehead_temperatures = temperature_matrix[forehead_mask]
print("提取出的额头温度数据:")
print(forehead_temperatures)
print(f"数据类型: {type(forehead_temperatures)}")
print(f"数据形状: {forehead_temperatures.shape}")

# 4. 详细解释提取过程
print("\n【步骤4】提取过程详解")
print("掩码为 True 的位置:")
true_positions = np.where(forehead_mask)
for i, (y, x) in enumerate(zip(true_positions[0], true_positions[1])):
    temp = temperature_matrix[y, x]
    print(f"  位置 [{y},{x}]: 掩码=True → 温度={temp}°C")

print(f"\n所以 temperature_matrix[forehead_mask] = {forehead_temperatures}")

# 5. 计算统计数据
print("\n【步骤5】计算统计数据")
print(f"  像素数量 (count): {forehead_temperatures.size}")
print(f"  最小温度 (min):   {np.min(forehead_temperatures):.2f}°C")
print(f"  最大温度 (max):   {np.max(forehead_temperatures):.2f}°C")
print(f"  平均温度 (mean):  {np.mean(forehead_temperatures):.2f}°C")
print(f"  标准差 (std):     {np.std(forehead_temperatures):.2f}°C")

# 6. 对比：如果掩码为 False 的区域
print("\n【步骤6】对比：非额头区域")
non_forehead_mask = ~forehead_mask  # 取反
non_forehead_temps = temperature_matrix[non_forehead_mask]
print(f"非额头区域 {non_forehead_temps.size} 个像素:")
print(f"  平均温度: {np.mean(non_forehead_temps):.2f}°C")

# 7. 完整过程可视化
print("\n【步骤7】完整过程可视化")
print("\n温度矩阵:              掩码:                提取结果:")
print("-" * 60)
for i in range(5):
    # 温度矩阵这一行
    temp_row = "  ".join([f"{temperature_matrix[i,j]:4.1f}" for j in range(5)])
    # 掩码这一行
    mask_row = "  ".join([" T " if forehead_mask[i,j] else " F " for j in range(5)])
    print(f"{temp_row}     {mask_row}", end="")
    
    # 如果这一行有True，显示提取的值
    if np.any(forehead_mask[i]):
        extracted = temperature_matrix[i][forehead_mask[i]]
        extracted_str = ", ".join([f"{v:.1f}" for v in extracted])
        print(f"  → {extracted_str}")
    else:
        print()

print("\n" + "=" * 60)
print("总结：掩码是'选择器'，告诉NumPy从哪些位置提取数据")
print("     matrix[mask] 会返回所有 mask==True 位置的值")
print("=" * 60)
