# ROI 温度统计工具套件

## 功能概览

三个脚本支持单个及批量处理热成像矩阵数据：

1. **roi_temp_stats_from_heatmap.py** - 单矩阵交互式 ROI 定义及统计
2. **roi_template_define.py** - 定义可复用的 ROI 模板（JSON）
3. **roi_batch_apply.py** - 批量应用模板并导出汇总表

## 工作流

### 方案 A：单矩阵快速标注（一次性用）

```bash
cd /home/shuwen/hospital-report

python3 scripts/roi_temp_stats_from_heatmap.py \
  --matrix-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1.csv \
  --out-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1_roi_stats.csv \
  --vmin 28 --vmax 40
```

交互操作：
- **左键** 在热图上点击添加顶点
- **右键** 撤销上一个点
- **n** 完成当前多边形（输入部位名，如 `forehead`）
- **c** 清空当前 ROI
- **q** 导出并退出

输出：`*_roi_stats.csv` 包含每个 ROI 的统计（count、min、max、mean、median、std、p05、p95）

---

### 方案 B：批量处理（推荐多张矩阵）

#### 步骤1：定义 ROI 模板

在参考矩阵上交互定义一套 ROI，保存为 JSON：

```bash
python3 scripts/roi_template_define.py \
  --matrix-csv data/35/2/1_B8A6B4E749D24C899104D4B846DE3E5F_1.csv \
  --out-json data/35/2/roi_template.json \
  --vmin 28 --vmax 40
```

同样的交互操作（左键加点、右键撤销、n确认、c清空、q保存退出）。

生成的 `roi_template.json` 结构：
```json
[
  {
    "name": "forehead",
    "vertices": [[x1, y1], [x2, y2], [x3, y3], ...]
  },
  {
    "name": "chest",
    "vertices": [[...], ...]
  }
]
```

#### 步骤2：批量应用模板到多个矩阵

```bash
python3 scripts/roi_batch_apply.py \
  --template-json data/35/2/roi_template.json \
  --matrix-dir data/35/2 \
  --out-summary data/35/2/roi_batch_summary.csv
```

输出：`roi_batch_summary.csv` 是宽格式表，每行一个矩阵，列为：
```
matrix_name | forehead_count | forehead_min | forehead_max | forehead_mean | ... | chest_count | chest_min | ...
```

可直接用于比对或导入 Excel/BI 工具做进一步分析。

---

## 统计指标说明

- **count** - ROI 内有效像素数
- **min/max** - 该 ROI 内最低/最高温度（℃）
- **mean** - 平均温度
- **median** - 中位数温度（对异常噪声更稳健）
- **std** - 标准差（温度分布均匀度指标）
- **p05/p95** - 5分位/95分位（排除极端值的稳健估计）

## 文件列表

- `roi_temp_stats_from_heatmap.py` - 单矩阵脚本
- `roi_template_define.py` - 模板定义脚本
- `roi_batch_apply.py` - 批量应用脚本
- `roi_workflow_README.md` - 本文件

## 依赖

- numpy
- matplotlib

安装（如未装）：
```bash
pip install numpy matplotlib
```

## 示例案例

假设 `data/35/2/` 下有多个病人的热成像矩阵：
```
1_xxx_1.csv
1_xxx_2.csv
2_yyy_1.csv
2_yyy_2.csv
...
```

### 快速上手：

1. 用第一张矩阵定义模板：
   ```bash
   python3 scripts/roi_template_define.py \
     --matrix-csv data/35/2/1_xxx_1.csv \
     --out-json data/35/2/roi_template.json
   ```

2. 批量应用：
   ```bash
   python3 scripts/roi_batch_apply.py \
     --template-json data/35/2/roi_template.json \
     --matrix-dir data/35/2 \
     --out-summary data/35/2/summary_all.csv
   ```

3. 打开 `summary_all.csv` 做对比分析或统计

---

## 故障排除

| 问题 | 解决方案 |
|------|--------|
| 窗口无响应 | 确保在有图形界面的环境（不能是纯 SSH 无 X11） |
| "未找到 CSV" | 检查路径和文件名 |
| ROI 为空 | 确保多边形顶点选择在矩阵范围内，至少 3 个点 |
| 汇总表为空 | 检查矩阵 CSV 是否格式正确（逗号分隔、二维） |

## 建议

- 定义 ROI 时要一致（比如都从額头中心开始，顺时针），这样模板在不同身体尺寸间可迁移性更好
- 先用小样本测试模板，再批量应用
- 定期备份 ROI 模板 JSON，便于后续复用或修改

