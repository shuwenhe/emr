# AI报告生成对比分析

## 📊 三种报告场景对比

### 场景1：AI完全启用 (OLLAMA_ENABLED=1)

#### 代码流程
```python
# analysis.py
OLLAMA_ENABLED = True
↓
llm_result = _generate_llm_diagnosis_and_opinion(llm_context)
↓
report["ai"] = {
    "diagnosis": "AI诊断文本",
    "doctor_opinion": "AI医生意见",
    "report_note": "AI补充说明",
    "treatment_plan_text": "AI方案说明"
}
```

#### JSON报告示例
```json
{
  "diagnosis": "温度范围 18.42C - 34.27C",
  "doctor_opinion": "基于热成像温度分布评估，风险等级为 low，建议结合临床进一步判断。",
  "ai": {
    "model": "qwen3:1.7b",
    "diagnosis": "患者全身热成像显示温度范围在18.42℃-34.27℃之间...",
    "doctor_opinion": "患者热成像检查结果显示区域温度分布不均匀...",
    "report_note": "本报告基于患者全身热成像数据生成，温度范围18.42-34.27℃...",
    "treatment_plan_text": "本治疗方案建议患者进行6次艾灸疗程..."
  },
  "treatment_plan": {
    "ai_recommendation": "本治疗方案建议患者进行6次艾灸疗程..."
  }
}
```

#### DOCX报告内容
```
红外热成像评估报告
─────────────────

患者信息
  姓名: 江小白
  性别: 男
  年龄: 34
  采集部位: 全身

温度指标
  最低温度: 18.42°C
  最高温度: 34.27°C
  平均温度: 26.32°C

风险等级
  LOW

诊断结论
  温度范围 18.42C - 34.27C

医生意见
  基于热成像温度分布评估，风险等级为 low，建议结合临床进一步判断。

治疗方案建议  ⭐ AI生成
  本治疗方案建议患者进行6次艾灸疗程，每3天进行一次治疗。
  根据热成像异常区域，针对r1_c1、r1_c3、r2_c3和r3_c2部位进行目标温热刺激，
  同时配合足三里和关元穴位的艾灸。...

补充说明  ⭐ AI生成
  本报告基于患者全身热成像数据生成，温度范围18.42-34.27℃，异常区域存在温度波动。
  建议结合临床检查，异常区域可能与局部代谢异常或血管异常相关，
  当前风险等级为低风险。仅供参考。

热成像图
  [图片]
```

**特点**：
- ✅ 有"补充说明"和"治疗方案建议"两个AI部分
- ✅ report.json中有"ai"字段
- ✅ 医学描述更专业和详细

---

### 场景2：AI被禁用 (OLLAMA_ENABLED=0)

#### 代码流程
```python
# analysis.py
OLLAMA_ENABLED = False
↓
llm_result = _generate_llm_diagnosis_and_opinion(...) if OLLAMA_ENABLED else {}
# 直接返回空dict，跳过AI调用
↓
report["ai"]  # 字段不存在或为空
```

#### JSON报告示例
```json
{
  "diagnosis": "温度范围 18.42C - 34.27C",
  "doctor_opinion": "基于热成像温度分布评估，风险等级为 low，建议结合临床进一步判断。",
  "ai": null,  // 或不存在此字段
  "treatment_plan": {
    // ai_recommendation 字段不存在
  }
}
```

#### DOCX报告内容
```
红外热成像评估报告
─────────────────

患者信息
  姓名: 江小白
  性别: 男
  年龄: 34
  采集部位: 全身

温度指标
  最低温度: 18.42°C
  最高温度: 34.27°C
  平均温度: 26.32°C

风险等级
  LOW

诊断结论
  温度范围 18.42C - 34.27C

医生意见
  基于热成像温度分布评估，风险等级为 low，建议结合临床进一步判断。

[无治疗方案建议]  ❌
[无补充说明]      ❌

热成像图
  [图片]
```

**特点**：
- ❌ 无"补充说明"章节
- ❌ 无"治疗方案建议"章节
- ❌ report.json无"ai"字段
- ⚠️ 内容较简洁（只有默认值）

---

### 场景3：AI调用失败 (OLLAMA不可用)

#### 代码流程
```python
# analysis.py 尝试调用
try:
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context)
    # ↓ Ollama服务不可达 / 超时 / 错误响应
    # ↓ 抛出异常
except:
    # ⚠️ analysis.py 中无 try-catch！
    # 异常直接传播，analyze_record() 失败
    
# report_docx.py 中有保护
try:
    ai_payload = generate_report_ai(report, emr)
    # ↓ 调用失败
except Exception as exc:
    logging.exception("LLM report generation failed")
    # 继续执行，DOCX仍会生成
```

#### 后果

**如果在 analyze_record() 中失败**：
```
analyze_record() 抛异常
    ↓
report.json 无法保存
    ↓
分析流程完全失败 ❌
```

**如果在 generate_docx_report() 中失败**：
```
generate_docx_report() 捕获异常
    ↓
DOCX仍会生成，但无"补充说明" ✅
    ↓
API返回 200，报告可用
```

**改进建议**：
```python
# 应该在 analysis.py 中也加入保护
try:
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context) if OLLAMA_ENABLED else {}
except Exception as exc:
    logging.exception("AI diagnosis generation failed")
    llm_result = {}  # 降级为默认值，不中断主流程
```

---

## 📈 内容质量对比

| 维度 | AI启用 | AI禁用 | AI失败 |
|------|-------|-------|-------|
| **诊断结论** | 来自数据 | 来自数据 | 来自数据 |
| **医生意见** | 默认模板 | 默认模板 | 默认模板 |
| **补充说明** | AI生成 ⭐ | 无 ❌ | 无 ❌ |
| **方案说明** | AI生成 ⭐ | 无 ❌ | 无 ❌ |
| **医学专业度** | 高 📚 | 中 📖 | 中 📖 |
| **临床指导性** | 高 ✅ | 低 ⚠️ | 低 ⚠️ |
| **文字长度** | 800+字 | 200字 | 200字 |

---

## 🔄 AI失败时的数据恢复

### 场景：Ollama服务不可达

#### 时间线
```
T0: analyze_record() 开始
T10: 尝试调用 Ollama（localhost:11434）
T15: 连接超时 (timeout=20s)
     └─ URLError: Connection refused
     
T16: 错误日志
     └─ Ollama generate error: URLError: Connection refused
     └─ Model: qwen3:1.7b, URL: http://localhost:11434
     
T17: _generate_llm_diagnosis_and_opinion() 返回 {}
T18: llm_result.get("diagnosis") → None
T19: ai_diagnosis = ""
T20: 使用默认值
     └─ diagnosis = summary  # "温度范围 18.42C - 34.27C"
     
T25: report.json 保存成功 (无"ai"字段)
T30: generate_docx_report() 检查 report["ai"] → 空 ⚠️
T35: 尝试实时调用 generate_report_ai()
     └─ 再次失败（Ollama仍不可用）
     
T40: logging.exception("LLM report generation failed")
T45: DOCX 仍保存成功 ✅
```

#### 恢复方案

**方案A：快速恢复（重启Ollama）**
```bash
# 1. 启动Ollama
ollama serve &

# 2. 重新生成报告
python3 -c "from app import api; api.regenerate_docx(record_id='...')"
```

**方案B：批量修复（重新分析）**
```bash
# 1. 列出无AI的报告
find data -name report.json -exec grep -L '"ai"' {} \;

# 2. 重新调用分析
for record_id in $(list_no_ai_records); do
    python3 -c "from app import analysis; analysis.analyze_record('$record_id')"
done
```

**方案C：缓存方案**
```python
# 为相同的患者+部位缓存AI结果
@lru_cache(maxsize=100)
def _generate_llm_diagnosis_and_opinion_cached(context_hash):
    # 基于context的hash缓存结果
    pass

# 下次相同参数时直接返回缓存
```

---

## 🎯 关键差异分析

### 代码流程差异

```
启用AI时                           禁用AI时
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

analyze_record()                  analyze_record()
  ↓                                ↓
OLLAMA_ENABLED? True ✓            OLLAMA_ENABLED? False ✗
  ↓                                ↓
_generate_llm_...()               llm_result = {}
  ↓                                ↓
POST to Ollama API                跳过API调用
  ↓                                ↓
Parse JSON response               (无远程调用)
  ↓                                ↓
extract ai["diagnosis"]           使用默认值
extract ai["doctor_opinion"]      diagnosis = summary
extract ai["report_note"]         doctor_opinion = template
  ↓                                ↓
report["ai"] = {...}              report["ai"] = None/不存在
  ↓                                ↓
save report.json                  save report.json
  ↓                                ↓
report_docx.py 使用现成的AI       report_docx.py 无AI可用
```

### 内容示例差异

#### 补充说明

**AI生成** ✨
```
本报告基于患者全身热成像数据生成，温度范围18.42-34.27℃，
异常区域存在温度波动。建议结合临床检查，异常区域可能与
局部代谢异常或血管异常相关，当前风险等级为低风险。
仅供参考。
```

**无AI** ❌
```
[无补充说明章节]
```

#### 治疗方案建议

**AI生成** ✨
```
本治疗方案建议患者进行6次艾灸疗程，每3天进行一次治疗。
根据热成像异常区域，针对r1_c1、r1_c3、r2_c3和r3_c2部位
进行目标温热刺激，同时配合足三里和关元穴位的艾灸。
治疗强度等级为3级，每次疗程时长约11分钟，目标温度为45℃。
请根据患者实际反应调整治疗强度与时间。仅供参考。
```

**无AI** ❌
```
[无治疗方案建议章节]
```

---

## ⚙️ 配置切换

### 启用AI
```bash
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen3:1.7b"
export OLLAMA_ENABLED="1"

# 或在代码中
os.environ["OLLAMA_ENABLED"] = "1"
```

### 禁用AI
```bash
export OLLAMA_ENABLED="0"

# 或在代码中
os.environ["OLLAMA_ENABLED"] = "0"
```

### 使用不同的LLM模型
```bash
# 更强大的模型（如果硬件允许）
export OLLAMA_MODEL="qwen2:7b"  # 更大的模型
export OLLAMA_MODEL="mistral"   # 不同的模型

# 更快的模型
export OLLAMA_MODEL="qwen3:1.7b"  # 当前（快速）
```

---

## 📝 总结

| 决策点 | AI启用 | AI禁用 |
|-------|-------|-------|
| **OLLAMA_ENABLED** | "1" | "0" |
| **analysis.py调用AI** | ✅ | ❌ |
| **report.json包含"ai"** | ✅ | ❌ |
| **DOCX有"补充说明"** | ✅ | ❌ |
| **DOCX有"方案建议"** | ✅ | ❌ |
| **内容来源** | AI + 规则 | 规则 + 默认值 |
| **医学专业度** | 高 | 中 |
| **生成速度** | 慢(网络I/O) | 快 |
| **成本** | Ollama资源 | CPU |
| **依赖性** | Ollama服务 | 无 |

