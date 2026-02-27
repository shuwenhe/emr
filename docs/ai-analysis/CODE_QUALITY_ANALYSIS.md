# AI报告代码质量与安全性分析

## 🔍 代码质量评估

### 1. 错误处理

#### ✅ 好的实践

**在 `_ollama_generate()` 中**：
```python
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
    result = json.loads(body)
    return str(result.get("response") or "").strip()
except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
    logging.error(f"Ollama generate error: {type(e).__name__}: {e}")
    logging.error(f"Model: {OLLAMA_MODEL}, URL: {OLLAMA_BASE_URL}")
    return ""
```

**优点**：
- ✅ 明确指定异常类型（不是通用 `Exception`）
- ✅ 记录详细日志（错误类型、模型、URL）
- ✅ 返回空字符串而非抛异常（降级处理）
- ✅ 20秒超时防止无限挂起

**在 `report_docx.py` 中**：
```python
try:
    ai_payload = generate_report_ai(report, emr)
    if ai_payload:
        report.setdefault("ai", ai_payload)
except Exception as exc:
    logging.exception("LLM report generation failed: %s", exc)
    # 继续执行，不中断DOCX生成
```

**优点**：
- ✅ 异常被捕获，不影响报告生成
- ✅ 使用 `logging.exception()` 自动包含堆栈跟踪
- ✅ 容错设计

#### ⚠️ 需要改进的地方

**在 `analysis.py` 中**：
```python
llm_result = _generate_llm_diagnosis_and_opinion(llm_context) if OLLAMA_ENABLED else {}
# ❌ 没有 try-catch！
# 如果 _ollama_generate() 中某个地方抛异常（不是预期的异常），
# 整个 analyze_record() 会失败
```

**改进方案**：
```python
try:
    llm_result = _generate_llm_diagnosis_and_opinion(llm_context) if OLLAMA_ENABLED else {}
except Exception as exc:
    logging.exception("AI diagnosis generation failed, using defaults")
    llm_result = {}  # 降级使用默认值
```

---

### 2. 配置管理

#### ✅ 环境变量方式

```python
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"
```

**优点**：
- ✅ 支持环境变量覆盖
- ✅ 有合理的默认值
- ✅ 跨文件一致（`analysis.py` 和 `llm_report.py` 都有）

**问题**：
- ⚠️ 代码重复（定义了两份）
- ⚠️ 不易集中管理
- ⚠️ 修改需要改两个地方

**改进方案**：
```python
# config.py 中统一定义
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"

# 在 analysis.py 和 llm_report.py 中导入
from .config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_ENABLED
```

---

### 3. JSON处理安全性

#### ✅ 防御性编程

**`_extract_json_block()` 的设计**：
```python
def _extract_json_block(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    
    # 方案1：直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    
    # 方案2：正则提取后解析
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    
    try:
        return json.loads(match.group(0))
    except Exception:
        return None  # 最后降级返回None
```

**优点**：
- ✅ 多层容错
- ✅ 不使用通用 `Exception`（使用特定异常）
- ✅ 正则提取可以从混合文本中获取JSON
- ✅ 防止完全失败

**潜在问题**：
- ⚠️ 正则 `\{.*\}` 过于贪心
  
  **示例**：
  ```
  输入: "Response: {a:1} and {b:2}"
  匹配: "{a:1} and {b:2}"  # 匹配了两个对象！
  ```
  
  **改进**：
  ```python
  # 使用更精确的正则
  import json
  
  def _extract_json_block_improved(text: str) -> Optional[dict]:
      for match in re.finditer(r'\{[^{}]*\}', text):
          try:
              return json.loads(match.group(0))
          except:
              continue
      return None
  ```

---

### 4. 字符串处理

#### ⚠️ 问题代码

```python
if ai_plan_text:
    ai_plan_text = _strip_think(
        ai_plan_text
        .replace("AI", "")        # ❌ 会删除 "人工" 中的 "AI"
        .replace("ＡＩ", "")      # ⚠️ 全角处理
        .strip()
    )
```

**问题示例**：
```
输入: "我们的人工智能系统生成了以下建议..."
输出: "我们的人工智能系统生成了以下建议..."  # 没有被修改

输入: "AI建议：患者应该..."
输出: "建议：患者应该..."  # 前缀被删除（符合预期）

输入: "这个ＡＩ系统是最棒的"
输出: "这个系统是最棒的"  # 删除了错误位置的字符
```

**根本问题**：  
使用 `.replace()` 而不是正则，会删除所有匹配的文本，包括不想删除的。

**改进方案**：
```python
def _clean_ai_prefix(text: str) -> str:
    """只删除开头的AI前缀"""
    if not text:
        return text
    
    # 只删除开头的AI前缀
    text = re.sub(r'^(ＡＩ|AI)[\s：:]*', '', text)
    return text.strip()

# 使用
ai_plan_text = _clean_ai_prefix(ai_plan_text)
```

---

### 5. 类型安全

#### ✅ 类型提示

```python
def _build_llm_context(
    patient: Dict[str, Any],
    body_part: str,
    summary: str,
    risk_level: str,
    metrics: Dict[str, Any],
    abnormal_regions: List[Dict[str, Any]],
) -> str:
```

**优点**：
- ✅ 明确的类型注解
- ✅ IDE可以提供自动完成
- ✅ 可以用 mypy 进行静态类型检查

#### ⚠️ 需要改进

```python
def generate_docx_report(report: Dict[str, Any], emr: Dict[str, Any]) -> Path:
    # ❌ Dict[str, Any] 太宽泛，无法验证结构
    
    # 改进：使用 TypedDict
    from typing import TypedDict
    
    class Report(TypedDict, total=False):
        report_id: str
        patient: Dict[str, Any]
        ai: Dict[str, str]
        treatment_plan: Dict[str, Any]
```

---

## 🔐 安全性分析

### 1. 输入验证

#### ⚠️ 问题：缺乏输入验证

```python
def _ollama_generate(prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
    # ❌ 没有验证 prompt 的长度
    # ❌ 没有验证 temperature 的范围
    # ❌ 没有验证 max_tokens 的范围
```

**可能的攻击**：
```python
# 超长提示词导致OOM
_ollama_generate("A" * 1000000)

# 无效参数
_ollama_generate("test", temperature=-999, max_tokens=-1)
```

**改进方案**：
```python
def _ollama_generate(
    prompt: str, 
    *, 
    temperature: float = 0.2, 
    max_tokens: int = 512
) -> str:
    # 输入验证
    if not prompt or len(prompt) > 10000:
        raise ValueError(f"Invalid prompt length: {len(prompt)}")
    
    if not 0 <= temperature <= 1:
        raise ValueError(f"temperature must be 0-1, got {temperature}")
    
    if not 1 <= max_tokens <= 2000:
        raise ValueError(f"max_tokens must be 1-2000, got {max_tokens}")
    
    # ... 继续执行
```

### 2. 输出验证

#### ✅ 好的实践

```python
def _generate_llm_diagnosis_and_opinion(context: str) -> Dict[str, str]:
    # ...
    result = {
        "diagnosis": str(data.get("diagnosis") or "").strip(),
        "doctor_opinion": str(data.get("doctor_opinion") or "").strip(),
        "report_note": str(data.get("report_note") or "").strip(),
    }
    
    # ✅ 检查字数长度
    def _too_short(value: str) -> bool:
        return len(value) < 80
    
    if any(_too_short(value) for value in result.values()):
        # 重新生成
```

#### ⚠️ 可改进

```python
# ❌ 没有检查过长的输出
# 如果AI生成了 100KB 的文本怎么办？

# 改进
MAX_OUTPUT_LENGTH = 5000  # 最多5000字符

for key, value in result.items():
    if len(value) > MAX_OUTPUT_LENGTH:
        result[key] = value[:MAX_OUTPUT_LENGTH]  # 截断
        logging.warning(f"Truncated {key} to {MAX_OUTPUT_LENGTH} chars")
```

### 3. 医学内容安全

#### ✅ 强制免责声明

```python
prompt = (
    context
    + "其中 doctor_opinion 和 report_note 必须明确'仅供参考'。"
)
```

#### ⚠️ 验证缺失

```python
# ❌ 没有验证AI是否真的包含了免责声明

def _verify_disclaimer(text: str) -> bool:
    return "仅供参考" in text or "仅作参考" in text

# 使用
if OLLAMA_ENABLED:
    ai_result = generate_report_ai(...)
    if ai_result.get("report_note"):
        if not _verify_disclaimer(ai_result["report_note"]):
            logging.warning("Missing disclaimer in AI report_note")
```

---

## 📊 性能分析

### 1. 网络I/O

**问题**：同步阻塞调用
```python
# analysis.py 中
llm_result = _generate_llm_diagnosis_and_opinion(llm_context)
# 这里会阻塞 20 秒（如果Ollama响应慢）
```

**影响**：
- 如果Ollama模型加载慢，整个API请求会挂起
- 用户体验差

**改进方案**：
```python
# 方案A：异步调用
import asyncio

async def _ollama_generate_async(prompt: str) -> str:
    # 使用 aiohttp 进行异步HTTP请求
    pass

# 方案B：后台任务
from celery import shared_task

@shared_task
def generate_ai_async(record_id: str):
    # 后台生成AI内容
    # 完成后更新数据库
    pass

# 方案C：缓存
from functools import lru_cache

@lru_cache(maxsize=1000)
def _generate_llm_diagnosis_and_opinion_cached(context_hash: str):
    # 相同context不重复调用
    pass
```

### 2. 内存使用

**问题**：大型JSON对象
```python
abnormal_regions = [
    {"region": "r1_c1", "avg_c": 18.48, ...},
    # ... 可能有数百个区域
]
```

**改进**：
```python
# 只保留异常的区域，而不是全部9个
abnormal_regions = [
    region for region in region_comparison
    if region.get("status") in {"high", "low"}
]
```

---

## 🧪 测试覆盖

### 现有代码的测试需求

#### 单元测试
```python
def test_extract_json_block():
    # 测试正常JSON
    assert _extract_json_block('{"a": 1}') == {"a": 1}
    
    # 测试混合文本中的JSON
    assert _extract_json_block('Response: {"a": 1}') == {"a": 1}
    
    # 测试无效JSON
    assert _extract_json_block('not json') is None
    
    # 测试空字符串
    assert _extract_json_block('') is None

def test_ollama_generate_timeout():
    # 模拟超时
    with patch('urllib.request.urlopen', side_effect=TimeoutError):
        result = _ollama_generate("test")
        assert result == ""

def test_too_short_content():
    # 测试内容长度验证
    llm_result = _generate_llm_diagnosis_and_opinion(context)
    assert len(llm_result["diagnosis"]) >= 80
```

#### 集成测试
```python
def test_full_analysis_with_ai():
    # 模拟Ollama服务
    with patch('_ollama_generate', return_value='{"diagnosis": "..."}'):
        result = analyze_record("test_id")
        
        assert "ai" in result
        assert result["ai"]["diagnosis"] is not None

def test_docx_generation_without_ai():
    # 测试AI不可用时的降级
    with patch('is_llm_enabled', return_value=False):
        path = generate_docx_report(report, {})
        
        # DOCX应该仍然生成
        assert path.exists()
```

---

## 📋 代码审查清单

### 必须修复（Critical）
- [ ] 为 `analyze_record()` 添加 try-catch
- [ ] 修改 `.replace("AI")` 为正则前缀匹配
- [ ] 统一配置常量定义位置

### 应该改进（Important）
- [ ] 添加输入验证（prompt长度等）
- [ ] 添加输出验证（字数上限等）
- [ ] 修复正则贪心匹配问题
- [ ] 为医学内容添加免责声明验证

### 可以优化（Nice to have）
- [ ] 实现异步AI调用
- [ ] 添加缓存机制
- [ ] 使用TypedDict改进类型安全
- [ ] 增加单元测试覆盖

---

## 📈 建议优先级

| 优先级 | 项目 | 工作量 | 收益 |
|-------|------|-------|------|
| 🔴 P0 | 添加 try-catch 保护 | 15分钟 | 防止流程中断 |
| 🔴 P0 | 修复 replace("AI") | 10分钟 | 防止误删医学内容 |
| 🟠 P1 | 统一配置管理 | 30分钟 | 易于维护 |
| 🟠 P1 | 正则表达式修复 | 20分钟 | 提高JSON提取准确度 |
| 🟡 P2 | 添加输入验证 | 1小时 | 安全加固 |
| 🟡 P2 | 异步AI调用 | 2小时 | 用户体验提升 |

