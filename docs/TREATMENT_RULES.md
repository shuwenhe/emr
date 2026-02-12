# 治疗方案规则配置说明

本文档说明 [config/treatment_rules.yaml](config/treatment_rules.yaml) 的字段含义与可配置范围。

## 1. 文件结构概览

```yaml
version: 1
keywords:
  - keyword: "颈"
    points:
      - name: "风池"
        reason: "缓解颈项紧张"
region_rules:
  - match: ["shoulder", "neck"]
    points:
      - name: "肩井"
        reason: "对应异常热区"
defaults:
  - name: "足三里"
    reason: "提升整体循环"
parameters:
  risk_levels:
    high:
      intensity_level: 1
      sessions: 10
      frequency: "daily"
  target_region:
    base_duration_min: 8
    duration_per_intensity: 1
    base_target_temp_c: 42
    temp_per_intensity: 1.0
    distance_cm: 3.0
  safety_limits:
    max_temp_c: 49.0
    max_duration_min: 20
  course_template: "建议 {sessions} 次为一疗程，频次 {frequency}，根据反应调整强度与时间。"
```

## 2. 字段说明

### 2.1 顶层
- `version`：规则版本号。
- `keywords`：基于诊断文本/部位关键词的穴位选择规则。
- `region_rules`：基于异常区域标签的穴位选择规则。
- `defaults`：未命中任何规则时的默认穴位。
- `parameters`：治疗参数与疗程配置。

### 2.2 keywords
- `keyword`：匹配诊断文本或部位字段的关键词（支持中文或英文）。
- `points`：穴位列表。
  - `name`：穴位名。
  - `reason`：选择原因，用于报告展示。

### 2.3 region_rules
- `match`：区域关键词数组，匹配异常区域字段（如 `neck`、`shoulder`、`背`）。
- `points`：对应穴位列表。

### 2.4 defaults
- 默认穴位集合，当前无规则命中时使用。

### 2.5 parameters

#### risk_levels
根据风险等级控制强度/疗程：
- `intensity_level`：强度等级（整数）。
- `sessions`：疗程次数。
- `frequency`：频次字符串（用于展示与设备调度）。

#### target_region
控制单次目标部位参数：
- `base_duration_min`：基础时长（分钟）。
- `duration_per_intensity`：每级强度增加时长。
- `base_target_temp_c`：基础目标温度（°C）。
- `temp_per_intensity`：每级强度增加温度。
- `distance_cm`：施灸距离（cm）。

#### safety_limits
- `max_temp_c`：安全上限温度（°C）。
- `max_duration_min`：安全上限时长（分钟）。

#### course_template
疗程建议模板，支持以下占位符：
- `{sessions}`：疗程次数
- `{frequency}`：频次
- `{intensity}`：强度等级

## 3. 修改建议

- 需要新增部位或诊断关键词时，优先加入 `keywords`。
- 需要根据异常区域细化穴位时，使用 `region_rules`。
- 如需个性化疗程策略，调整 `parameters.risk_levels`。

## 4. 生效范围

规则由后端在分析阶段读取并生成治疗方案，影响：
- 接口返回的 `treatment_plan`
- 报告文档中的“针对性治疗方案”章节
