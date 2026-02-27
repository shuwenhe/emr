# AI生成报告代码分析

## 📋 概述

医疗热成像分析系统使用 **Ollama大语言模型**（默认qwen3:1.7b）生成医学诊断和建议，完全集成到报告生成流程中。

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────┐
│         数据采集和分析层 (analysis.py)             │
│  - 读取CSV热成像数据                               │
│  - 计算温度指标、风险等级                          │
│  - 基于规则引擎生成治疗方案                        │
│  - **调用AI生成诊断**                              │
└────────────┬────────────────────────────────────────┘
             │ 保存 JSON 报告
             ↓
┌─────────────────────────────────────────────────────┐
│         JSON报告数据库 (report.json)               │
│  - 基础数据（患者、温度指标）                      │
│  - **AI数据（診斷、建議、補充說明）**              │
│  - 治疗方案和其他分析结果                          │
└────────────┬────────────────────────────────────────┘
             │ 读取
             ↓
┌─────────────────────────────────────────────────────┐
│      DOCX报告生成层 (report_docx.py)               │
│  - 从JSON提取AI生成内容                            │
│  - 如果JSON中无AI内容，调用AI生成（备用）         │
│  - 将AI内容插入DOCX                                │
└──────────────────┬────────────────────────────────┘
                   │ 保存
                   ↓
              DOCX报告文件
```

---

## 🔧 核心模块详解

### 1️⃣ **llm_report.py** - AI生成引擎

#### 关键配置
```python
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"
```

**说明**：
- 默认使用本地Ollama服务（localhost:11434）
- 模型为qwen3:1.7b（通义千问）
- 通过环境变量控制启用/禁用

#### 关键函数

##### A. `_ollama_generate()` - 调用LLM
```python
def _ollama_generate(prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str
```

**功能**：向Ollama服务发送提示词，获取生成的文本

**参数**：
- `prompt`: 提示词内容
- `temperature`: 0.2（低温度 = 确定性强）
- `max_tokens`: 最大生成词数

**请求格式**：
```json
{
  "model": "qwen3:1.7b",
  "prompt": "你是一名医疗热成像评估助手...",
  "stream": false,
  "options": {
    "temperature": 0.2,
    "num_predict": 512
  }
}
```

**错误处理**：
- URLError / HTTPError：网络连接失败
- TimeoutError：请求超时（20秒限制）
- JSONDecodeError：响应解析失败
- 所有错误均记录日志，返回空字符串

---

##### B. `_extract_json_block()` - JSON提取器
```python
def _extract_json_block(text: str) -> Optional[dict]
```

**功能**：从LLM生成的文本中提取JSON数据

**流程**：
1. 先尝试直接 JSON.parse()
2. 如果失败，使用正则 `\{.*\}` 匹配JSON块
3. 再次尝试解析匹配到的字符串
4. 如果全部失败，返回None

**示例**：
```
输入: "我生成的是这样的: {\"diagnosis\": \"...\", \"doctor_opinion\": \"...\"}"
输出: {"diagnosis": "...", "doctor_opinion": "..."}
```

---

##### C. `_build_llm_context()` - 上下文构建器
```python
def _build_llm_context(report: Dict[str, Any], emr: Dict[str, Any]) -> str
```

**功能**：为AI生成构建完整的医学上下文

**包含信息**：
```
患者信息：姓名、性别、年龄、采集部位
风险等级：low / medium / high
温度摘要：整体温度范围和分布
温度指标：最低、最高、平均温度
异常区域：具体区域名称、温度值、偏差
```

**示例输出**：
```
你是一名医疗热成像评估助手。请基于以下信息生成简洁、谨慎的中文内容。输出只需客观结论，避免夸大或绝对化表述。
患者信息：姓名=江小白 性别=male 年龄=34 部位=全身
风险等级：low
温度摘要：温度范围 18.42C - 34.27C
温度指标：min=18.42 max=34.27 avg=26.32
异常区域：[{'region': 'r1_c1', 'avg_c': 18.48, 'status': 'low', 'delta_c': -7.84}, ...]
```

---

##### D. `_generate_llm_diagnosis_and_opinion()` - 诊断生成器
```python
def _generate_llm_diagnosis_and_opinion(context: str) -> Dict[str, str]
```

**功能**：生成诊断、医生意见和报告备注

**生成字段**：
| 字段 | 说明 | 最小长度 |
|------|------|---------|
| `diagnosis` | 基于热成像的诊断结论 | 80字 |
| `doctor_opinion` | 医生评价（必须含"仅供参考"） | 80字 |
| `report_note` | 补充说明（必须含"仅供参考"） | 80字 |

**两轮生成机制**：
```python
# 第一轮：基础生成
prompt_v1 = "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note。"
           + "每个字段输出 3-5 句中文，不少于 80 字..."

# 检查字数，如果 < 80字，进行第二轮
prompt_v2 = "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note。"
           + "请输出更详细的内容，每个字段不少于 120 字，分为 3-5 句..."
```

**质量控制**：
- 如果生成内容过短（<80字），自动重新生成
- 失败时保留第一轮结果

---

##### E. `_generate_llm_plan_text()` - 治疗方案说明生成器
```python
def _generate_llm_plan_text(context: str, plan: Dict[str, Any]) -> str
```

**功能**：为规则引擎生成的治疗方案生成自然语言说明

**输入方案信息**：
```json
{
  "intensity_level": 3,
  "sessions": 6,
  "frequency": "every_3_days",
  "target_regions": [...],
  "acupoints": [{"name": "足三里", "reason": "提升整体循环"}, ...]
}
```

**生成要求**：
- 3-6句简洁中文
- 涵盖频次、疗程、关键部位
- 必须标注"仅供参考"
- `temperature=0.3`（比诊断生成更随机）
- `max_tokens=500`

**示例输出**：
```
本治疗方案建议患者进行6次艾灸疗程，每3天进行一次治疗。
针对异常部位（r1_c1、r1_c3等）进行目标区域温热刺激，
配合足三里和关元穴位，强度等级为3级。
治疗时长每次约11分钟，目标温度45℃。
请根据患者实际反应调整治疗强度和时间。仅供参考。
```

---

##### F. `generate_report_ai()` - 主函数
```python
def generate_report_ai(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, Any]
```

**功能**：协调所有AI生成任务，返回完整的AI payload

**执行流程**：
```python
1. 检查 OLLAMA_ENABLED
2. 构建LLM上下文 (_build_llm_context)
3. 生成诊断和意见 (_generate_llm_diagnosis_and_opinion)
4. 生成治疗方案说明 (_generate_llm_plan_text)
5. 汇总所有结果返回
```

**返回格式**：
```json
{
  "model": "qwen3:1.7b",
  "diagnosis": "基于热成像数据分析...",
  "doctor_opinion": "患者整体热分布...仅供参考。",
  "report_note": "本报告基于热成像数据生成...仅供参考。",
  "treatment_plan_text": "建议6次疗程，每3天一次..."
}
```

---

### 2️⃣ **report_docx.py** - DOCX生成层

#### 关键函数

##### A. `generate_docx_report()` - 主报告生成器

**执行流程**：

```python
1. 解析患者信息和温度指标
2. 确定输出文件路径
   - 格式：reports/{YYYYMMDD}/{患者名}{YYYYMMDDHHMMSS}.docx
   - 使用生成时间（而非采集时间）

3. 添加基础信息段
   - 标题、报告ID、采集时间
   - 患者信息（性别中文化）
   - 温度指标

4. 添加诊断和意见
   - 诊断结论
   - 医生意见

5. 添加AI内容（核心）：
   ┌─────────────────────────────────────────┐
   │  从 report.json 读取 "ai" 字段          │
   │  ├─ 如果有：直接使用                    │
   │  └─ 如果无且LLM启用：实时调用生成      │
   │                                        │
   │  处理治疗方案建议                       │
   │  处理补充说明                          │
   │  （清理 <think> 标签和 "AI" 文本）     │
   └─────────────────────────────────────────┘

6. 添加热成像图
7. 保存文件
```

---

##### B. AI内容的条件逻辑（关键！）

```python
# 第一步：获取或生成AI内容
ai_payload = report.get("ai") or {}  # 从JSON读取

if not ai_payload and is_llm_enabled():
    try:
        ai_payload = generate_report_ai(report, emr)  # 实时生成
        if ai_payload:
            report.setdefault("ai", ai_payload)  # 保存到report
    except Exception as exc:
        logging.exception("LLM report generation failed: %s", exc)
        # 失败时 ai_payload 仍为空dict，继续使用默认值

# 第二步：提取和处理文本
ai_plan_text = ""
ai_report_note = str(ai_payload.get("report_note") or "").strip()

# 三重获取治疗方案文本
plan = report.get("treatment_plan") or {}
if isinstance(plan, dict):
    ai_plan_text = str(plan.get("ai_recommendation") or "").strip()  # 方案内的推荐
if not ai_plan_text:
    ai_plan_text = str(ai_payload.get("treatment_plan_text") or "").strip()  # AI生成的文本
    if ai_plan_text and isinstance(plan, dict):
        plan["ai_recommendation"] = ai_plan_text  # 同步回方案

# 第三步：清理和插入
if ai_plan_text:
    ai_plan_text = _strip_think(
        ai_plan_text
        .replace("AI", "")        # 移除"AI"前缀
        .replace("ＡＩ", "")      # 移除全角"ＡＩ"
        .strip()
    )

if ai_report_note:
    ai_report_note = _strip_think(
        ai_report_note
        .replace("AI", "")
        .replace("ＡＩ", "")
        .strip()
    )

# 第四步：插入DOCX
if ai_plan_text:
    doc.add_heading("治疗方案建议", level=2)
    doc.add_paragraph(ai_plan_text)

if ai_report_note:
    doc.add_heading("补充说明", level=2)
    doc.add_paragraph(ai_report_note)
```

---

## 🔄 完整的数据流

### 场景1：正常流程（AI已生成）

```
analysis.py
  ├─ 读取CSV温度数据
  ├─ 调用 _ollama_generate()
  ├─ 获得诊断、意见、补充说明
  └─ 保存到 report.json["ai"]
       ↓
report_docx.py
  ├─ 读取 report.json
  ├─ 检查 report["ai"] 存在 ✓
  ├─ 直接提取 ai["report_note"]
  └─ 插入DOCX → "补充说明"
```

### 场景2：备用流程（DOCX生成时AI不存在）

```
report.json (无"ai"字段)
  ↓
report_docx.py
  ├─ 检查 report["ai"] 为空 ✗
  ├─ 检查 is_llm_enabled() = true
  ├─ 调用 generate_report_ai()
  │  └─ 实时调用Ollama生成AI内容
  ├─ 提取 ai_payload["report_note"]
  └─ 插入DOCX → "补充说明"
```

---

## ⚙️ 生成质量控制

### 1. 提示词策略
```python
temperature = 0.2  # 诊断用（低温度=确定性高）
temperature = 0.3  # 治疗方案用（稍高=更多样性）
```

### 2. 内容长度要求
```
第一轮：80字 min
第二轮：120字 min（如果第一轮失败）
```

### 3. 强制标注
```python
# 提示词明确要求
"doctor_opinion 和 report_note 必须明确'仅供参考'。"
```

### 4. 错误恢复
```python
if _too_short(value):  # 字数不足
    retry_prompt(...)   # 重新生成
    merge_with_fallback  # 失败时保留之前的结果
```

---

## 🛡️ 数据安全性

### 1. 本地处理
- Ollama服务运行在本地（localhost）
- 不上传到云端

### 2. 医学谨慎性
```python
# 强制要求
"输出只需客观结论，避免夸大或绝对化表述。"
"必须包含'仅供参考'免责声明"
```

### 3. 失败容错
```python
if not OLLAMA_ENABLED:
    return ""  # AI被禁用则返回空

try:
    ai_payload = generate_report_ai()
except Exception:
    logging.exception(...)  # 记录异常
    # 继续使用默认规则生成的内容
```

---

## 📊 配置示例

### 启用AI报告生成
```bash
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen3:1.7b"
export OLLAMA_ENABLED="1"
```

### 禁用AI报告生成
```bash
export OLLAMA_ENABLED="0"
```

---

## 🎯 关键要点总结

| 功能 | 实现位置 | 触发时机 | 质量保证 |
|------|--------|--------|--------|
| **诊断生成** | llm_report.py | analysis.py | 2轮生成+字数检查 |
| **意见生成** | llm_report.py | analysis.py | 必须包含"仅供参考" |
| **补充说明** | llm_report.py | analysis.py | 120字最小 |
| **方案说明** | llm_report.py | analysis.py | 3-6句+标注 |
| **DOCX生成** | report_docx.py | 报告请求 | 实时/备用双路线 |
| **内容清理** | report_docx.py | DOCX插入前 | 移除思考过程 |

---

## 📝 常见问题

**Q: 为什么有些报告没有"补充说明"？**  
A: 原因可能是：
1. OLLAMA_ENABLED=0（AI被禁用）
2. Ollama服务不可用
3. AI生成失败但已记录日志

**Q: AI内容保存在哪里？**  
A: 
- JSON报告：`data/{record_id}/report.json` → `report["ai"]` 字段
- DOCX报告：`reports/{YYYYMMDD}/{患者名}{时间戳}.docx` → "补充说明" 段

**Q: 如何验证AI是否生成了内容？**  
A: 
1. 检查 `report.json` 是否有 `"ai"` 字段
2. 查看 DOCX 是否有 "补充说明" 或 "治疗方案建议" 章节
3. 检查服务器日志是否有 Ollama 调用记录

**Q: 为什么某个字段为空？**  
A: AI生成时该字段内容被评估为过短（<80字），自动重新生成时可能仍失败，保留了之前的空值。
