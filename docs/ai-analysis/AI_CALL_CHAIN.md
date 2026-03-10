# AI报告生成调用链分析

## 🔗 执行流程追踪

### 完整调用栈

```
analyze_record() [analysis.py]
    ↓
    ├─ 第1步：加载和分析数据
    │   ├─ 读取CSV温度数据
    │   ├─ 计算温度指标和风险等级
    │   └─ 区域对比分析
    │
    ├─ 第2步：**AI诊断生成** ⭐
    │   ├─ 构建LLM上下文
    │   │   └─ _build_llm_context(patient, body_part, summary, risk_level, ...)
    │   │
    │   └─ 调用AI生成诊断
    │       └─ _generate_llm_diagnosis_and_opinion(context)
    │           ├─ 调用 _ollama_generate(prompt) → LLM
    │           ├─ 提取JSON字段：diagnosis, doctor_opinion, report_note
    │           └─ 如果字数不足，重新生成
    │
    ├─ 第3步：规则引擎生成治疗方案
    │   └─ _build_treatment_plan() [纯规则引擎，非AI]
    │
    ├─ 第4步：**AI方案说明生成** ⭐
    │   └─ _generate_llm_plan_text(context, plan)
    │       └─ 调用 _ollama_generate(prompt) → LLM
    │
    ├─ 第5步：汇总数据
    │   └─ 将AI结果保存到 report["ai"]
    │
    └─ 第6步：保存报告
        └─ report.json (包含"ai"字段)
             ↓
        后续DOCX生成时使用该数据
```

---

## 📍 关键代码片段

### analysis.py 中的AI调用

#### 代码位置1：诊断生成入口（第~543行）

```python
def analyze_record(record_id: str) -> Dict[str, Any]:
    # ... 前面的数据处理代码 ...
    
    # 第1步：构建LLM上下文
    llm_context = _build_llm_context(
        patient=patient,
        body_part=body_part,
        summary=summary,
        risk_level=risk_level,
        metrics=metrics,
        abnormal_regions=abnormal_regions,
    )
    
    # 第2步：调用AI生成诊断和意见
    # ⭐ 关键行：仅当 OLLAMA_ENABLED=true 时执行
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context) if OLLAMA_ENABLED else {}
    
    # 提取AI生成的三个字段
    ai_diagnosis = str(llm_result.get("diagnosis") or "").strip()
    ai_doctor_opinion = str(llm_result.get("doctor_opinion") or "").strip()
    ai_report_note = str(llm_result.get("report_note") or "").strip()
    
    # 第3步：AI内容与默认值的逻辑
    if not diagnosis and ai_diagnosis:
        diagnosis = ai_diagnosis  # AI诊断用于替代（如果原诊断为空）
    
    if not doctor_opinion and ai_doctor_opinion:
        doctor_opinion = ai_doctor_opinion  # AI意见用于替代
    
    # 如果都是空，使用默认值
    if not doctor_opinion:
        doctor_opinion = f"基于热成像温度分布评估，风险等级为 {risk_level}，建议结合临床进一步判断。"
    
    if not diagnosis:
        diagnosis = summary if summary else "影像学提示无明显异常"
    
    # ... 其他处理 ...
```

#### 代码位置2：治疗方案说明生成（第~625行）

```python
def analyze_record(record_id: str) -> Dict[str, Any]:
    # ... 前面的代码 ...
    
    # 第1步：规则引擎生成治疗方案（非AI）
    plan = _build_treatment_plan(
        record_id, plan_id, capture_time,
        diagnosis, body_part, risk_level, abnormal_regions,
    )
    
    # 第2步：为方案生成AI说明文字
    ai_plan_text = ""
    if OLLAMA_ENABLED:
        ai_plan_text = _generate_llm_plan_text(llm_context, plan).strip()
        if ai_plan_text:
            plan["ai_recommendation"] = ai_plan_text  # 保存到方案
    
    # ... 保存JSON报告 ...
    
    # 第3步：汇总AI内容
    if OLLAMA_ENABLED and (ai_diagnosis or ai_doctor_opinion or ai_plan_text or ai_report_note):
        report["ai"] = {
            "model": OLLAMA_MODEL,
            "diagnosis": ai_diagnosis,
            "doctor_opinion": ai_doctor_opinion,
            "treatment_plan_text": ai_plan_text,
            "report_note": ai_report_note,
        }
    
    # ... 返回报告 ...
```

---

## 🔍 AI内容的两处生成点

### 📌 生成点1：analysis.py（推荐的地方）

**何时执行**：  
- 每次调用 `analyze_record()` 时

**优势**：
- 原始数据最新鲜
- AI和规则引擎一起执行
- 结果保存在JSON中

**参数流**：
```
CSV数据 → 计算指标 → 构建上下文 → 调用LLM → 保存JSON
```

### 📌 生成点2：report_docx.py（备用的地方）

**何时执行**：  
- 当 `report["ai"]` 为空且 `OLLAMA_ENABLED=true` 时
- 生成DOCX报告文件时

**优势**：
- 冗余保障机制
- 降低漏检风险

**参数流**：
```
report.json（可能无ai字段） → 检查为空 → 实时调用LLM → 获得内容 → 插入DOCX
```

---

## ⚙️ 参数详解

### _build_llm_context() 输入

```python
_build_llm_context(
    patient={
        'patient_id': 'P28CFDEDE92AF',
        'name': '江小白',
        'gender': 'male',
        'age': 34,
        'body_part': '全身',
    },
    body_part='全身',
    summary='温度范围 18.42C - 34.27C',
    risk_level='low',
    metrics={
        'min_c': 18.42,
        'max_c': 34.27,
        'avg_c': 26.32,
        'count': 12,
    },
    abnormal_regions=[
        {'region': 'r1_c1', 'status': 'low', 'avg_c': 18.48, 'delta_c': -7.84},
        {'region': 'r1_c3', 'status': 'high', 'avg_c': 31.45, 'delta_c': 5.13},
        {'region': 'r2_c3', 'status': 'high', 'avg_c': 34.12, 'delta_c': 7.8},
        {'region': 'r3_c2', 'status': 'low', 'avg_c': 21.23, 'delta_c': -5.09},
    ],
)
```

### _generate_llm_diagnosis_and_opinion() 输出

```python
{
    "diagnosis": "患者全身热成像显示温度范围在18.42℃-34.27℃之间，平均温度26.32℃。"
                 "存在局部温度异常区域，其中r1_c1和r3_c2区域温度偏低，"
                 "r1_c3和r2_c3区域温度偏高。整体风险等级为低风险，"
                 "未见明显的全身性异常。建议结合临床症状进一步评估。",
    
    "doctor_opinion": "患者热成像检查结果显示区域温度分布不均匀，"
                      "存在局部热异常。低温区域可能反映局部代谢相对不足，"
                      "高温区域可能与局部血流量增加相关。建议结合临床检查和病史，"
                      "排除病理性异常。仅供参考。",
    
    "report_note": "本报告基于患者全身热成像数据生成，温度范围18.42-34.27℃，"
                   "异常区域存在温度波动。建议结合临床检查，"
                   "异常区域可能与局部代谢异常或血管异常相关，"
                   "当前风险等级为低风险。仅供参考。"
}
```

### _generate_llm_plan_text() 输出

```python
"本治疗方案建议患者进行6次艾灸疗程，每3天进行一次治疗。"
"根据热成像异常区域，针对r1_c1、r1_c3、r2_c3和r3_c2部位进行目标温热刺激，"
"同时配合足三里和关元穴位的艾灸。治疗强度等级为3级，每次疗程时长约11分钟，"
"目标温度为45℃，距离保持在3厘米。建议根据患者实际反应调整治疗强度和时间。"
"仅供参考。"
```

---

## 🎯 关键决策点

### 判断1：是否调用AI？

```python
# analysis.py 第543行
if OLLAMA_ENABLED:  # ← 控制开关
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context)
else:
    llm_result = {}  # 返回空dict，使用默认值
```

**影响**：  
- `OLLAMA_ENABLED=1` → 始终调用AI  
- `OLLAMA_ENABLED=0` → 完全跳过AI，仅用规则引擎和默认值

### 判断2：使用AI结果还是默认值？

```python
# 诊断采用顺序
if diagnosis:                    # 优先：原始诊断（来自EMR）
    pass
elif ai_diagnosis:               # 次选：AI诊断
    diagnosis = ai_diagnosis
else:                            # 降级：默认值
    diagnosis = summary or "影像学提示无明显异常"

# 医生意见采用顺序
if doctor_opinion:               # 优先：原始意见（来自EMR）
    pass
elif ai_doctor_opinion:          # 次选：AI意见
    doctor_opinion = ai_doctor_opinion
else:                            # 降级：默认模板
    doctor_opinion = f"基于热成像温度分布评估，风险等级为 {risk_level}..."
```

**特点**：  
- AI不会覆盖现有的医生输入
- AI是补充而非替代
- 总有默认值保底

### 判断3：如何处理AI生成失败？

```python
try:
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context)
except Exception:
    # ⚠️ analysis.py 中没有try-catch
    # 错误会直接传播
    raise

# 在 report_docx.py 中有保护
try:
    ai_payload = generate_report_ai(report, emr)
except Exception as exc:
    logging.exception("LLM report generation failed: %s", exc)
    # 继续执行，DOCX仍会生成，但无AI内容
```

**风险**：  
- `analyze_record()` 中失败会导致整个分析失败 ❌
- `generate_docx_report()` 中失败不影响报告生成 ✅

---

## 📊 数据流向图

```
┌─────────────────────────────┐
│   CSV 温度数据文件          │
└──────────────┬──────────────┘
               │ 读取
               ↓
┌──────────────────────────────────┐
│ analyze_record(record_id)         │
├──────────────────────────────────┤
│                                  │
│ 1. 解析数据 (纯计算)             │
│    ├─ min/max/avg 温度           │
│    ├─ risk_level                 │
│    └─ abnormal_regions           │
│                                  │
│ 2. **构建 LLM 上下文** ⭐        │
│    └─ _build_llm_context()       │
│                                  │
│ 3. **调用 AI 生成** ⭐⭐⭐       │
│    ├─ _ollama_generate()         │
│    │  └─ POST to Ollama API      │
│    └─ 提取诊断/意见/补充说明    │
│                                  │
│ 4. 规则引擎生成方案             │
│    └─ _build_treatment_plan()    │
│                                  │
│ 5. **AI生成方案说明** ⭐        │
│    └─ _generate_llm_plan_text()  │
│                                  │
│ 6. 汇总数据到 report["ai"]       │
│                                  │
└──────────────┬──────────────────┘
               │ 保存 JSON
               ↓
┌─────────────────────────────┐
│  report.json (含"ai"字段)    │
└──────────────┬──────────────┘
               │ 读取
               ↓
┌──────────────────────────────────┐
│ generate_docx_report()           │
├──────────────────────────────────┤
│                                  │
│ 1. 提取 report["ai"]             │
│                                  │
│ 2. 如果为空 & LLM启用           │
│    └─ 实时调用 generate_report() │
│                                  │
│ 3. 清理文本                      │
│    ├─ 移除 <think> 标签          │
│    ├─ 移除 "AI" 前缀             │
│    └─ strip() 清理               │
│                                  │
│ 4. 插入 DOCX                     │
│    ├─ "补充说明" 段              │
│    └─ "治疗方案建议" 段          │
│                                  │
└──────────────┬──────────────────┘
               │ 保存
               ↓
┌─────────────────────────────┐
│  DOCX 报告文件              │
│  (含AI生成的"补充说明")    │
└─────────────────────────────┘
```

---

## ✅ 验证AI内容是否被使用

### 方法1：查看JSON报告

```bash
# 查看是否有"ai"字段
cat /home/shuwen/emr/data/{record_id}/report.json | grep -A 20 '"ai"'

# 预期输出：
# "ai": {
#   "model": "qwen3:1.7b",
#   "diagnosis": "...",
#   "doctor_opinion": "...",
#   "report_note": "...",
#   "treatment_plan_text": "..."
# }
```

### 方法2：查看DOCX报告

```bash
# 提取DOCX文本，查看是否有"补充说明"
python3 << 'EOF'
from zipfile import ZipFile
import xml.etree.ElementTree as ET

with ZipFile('/path/to/report.docx', 'r') as z:
    xml = z.read('word/document.xml').decode()

root = ET.fromstring(xml)
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

for t in root.findall('.//w:t', ns):
    if '补充说明' in (t.text or ''):
        print("✓ 找到AI生成的补充说明")
        break
EOF
```

### 方法3：查看服务器日志

```bash
# 检查Ollama调用日志
grep -i "ollama\|llm\|generate" /var/log/emr/*.log

# 应该看到类似：
# INFO: Ollama generate: model=qwen3:1.7b, tokens=512
# INFO: LLM response received: diagnosis="..."
```

---

## 🚨 故障排查

### 问题1：DOCX中没有"补充说明"

**可能原因**：
```
□ OLLAMA_ENABLED=0
  └─ 解决：export OLLAMA_ENABLED="1"

□ Ollama服务未启动
  └─ 解决：ollama serve &

□ report.json中有"ai"字段但为空
  └─ 解决：检查 AI 调用是否失败

□ llm_report.py 中的生成失败
  └─ 解决：检查日志 "LLM report generation failed"
```

### 问题2：AI内容重复或被截断

**可能原因**：
```
□ Ollama返回的JSON格式错误
  └─ 解决：查看 _extract_json_block() 的处理

□ 文本被 _strip_think() 过度清理
  └─ 解决：检查是否误删了有效内容

□ 字数限制导致内容被截断
  └─ 解决：增加 max_tokens 参数
```

### 问题3：AI生成延迟报告生成

**解决方案**：
```python
# 方案A：异步生成（目前未实现）
async def generate_ai_async(context):
    # 不阻塞主流程

# 方案B：增加超时时间
_ollama_generate(..., timeout=30)  # 从20秒改为30秒

# 方案C：使用缓存
@lru_cache(maxsize=100)
def _ollama_generate(prompt):
    # 避免相同提示词重复调用
```

