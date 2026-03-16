# 按 `report_sections` 分字段检索接口设计

## 目标

当前实现中，`generate_report_ai()` 只做一次统一检索，然后把同一批上下文同时喂给：

- `diagnosis`
- `doctor_opinion`
- `report_note`
- `treatment_plan_text`

这会带来两个问题：

1. 诊断类字段容易混入治疗建议类知识。
2. 治疗建议类字段容易混入纯判读原则或写作模板。

目标是把检索拆成“按报告字段定制的多路检索”，并保持与现有数据结构兼容。

## 当前接入点

现有调用链：

- [`ingest.py`](/home/shuwen/emr/route/ingest.py)
- [`AIService.generate_report_summary()`](/home/shuwen/emr/service/ai/__init__.py)
- [`generate_report_ai()`](/home/shuwen/emr/ingestion/app/llm_report.py)

现有回写字段：

- `diagnosis`
- `doctor_opinion`
- `report_note`
- `treatment_plan_text`
- `retrieved_context`
- `retrieved_items`
- `citations`
- `evidence_item_ids`
- `diagnosis_evidence_item_ids`
- `plan_evidence_item_ids`

## 设计原则

- 保持向后兼容，不破坏旧字段。
- 新增“分字段检索结果”，但保留聚合结果。
- 检索过滤优先使用知识条目中的 `report_sections`。
- 后续如果接向量库，也先做字段过滤，再做召回或重排。

## 接口分层

建议拆成三层函数：

### 1. 查询构造层

新增函数：

```python
def build_section_queries(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, str]:
    ...
```

返回示例：

```json
{
  "diagnosis": "腰背部 热成像 左右温差 0.8°C 中风险 局部高温",
  "doctor_opinion": "腰背部 中风险 局部高温 医生意见 复评 转诊提醒",
  "report_note": "热成像检查前准备 报告说明 风险分层 仅供参考",
  "treatment_plan_text": "腰背部 中风险 异常ROI 理疗 灸疗 复评 7-14天"
}
```

建议规则：

- `diagnosis`
  - 强调：部位、模式、温差、风险等级、异常区域
- `doctor_opinion`
  - 强调：解释、谨慎措辞、红旗症状、复评建议
- `report_note`
  - 强调：SOP、报告说明、适用边界、免责声明
- `treatment_plan_text`
  - 强调：治疗频次、疗程、目标区域、复评、禁忌

### 2. 检索执行层

新增函数：

```python
def retrieve_context_by_section(
    queries: Dict[str, str],
    *,
    top_k_map: Optional[Dict[str, int]] = None,
    record_id: str = "unknown",
) -> Dict[str, Any]:
    ...
```

返回示例：

```json
{
  "sections": {
    "diagnosis": {
      "query": "...",
      "items": [...],
      "citations": [...],
      "context": "..."
    },
    "doctor_opinion": {
      "query": "...",
      "items": [...],
      "citations": [...],
      "context": "..."
    },
    "report_note": {
      "query": "...",
      "items": [...],
      "citations": [...],
      "context": "..."
    },
    "treatment_plan_text": {
      "query": "...",
      "items": [...],
      "citations": [...],
      "context": "..."
    }
  },
  "merged": {
    "items": [...],
    "citations": [...],
    "context": "..."
  }
}
```

### 3. 生成消费层

把每个字段只喂给对应上下文：

- `diagnosis` 使用 `sections["diagnosis"]`
- `doctor_opinion` 使用 `sections["doctor_opinion"]`
- `report_note` 使用 `sections["report_note"]`
- `treatment_plan_text` 使用 `sections["treatment_plan_text"]`

保留一个 `merged.context`，用于兼容旧逻辑和调试。

## 检索过滤规则

### 基础过滤

在 `_load_kb_items()` 中保留这些字段：

- `category`
- `report_sections`
- `priority`
- `status`
- `risk_levels`
- `body_parts`
- `retrieval_hints`

建议把当前函数从“只保留少数字段”升级为“保留结构化元数据”。

### 分字段过滤

新增函数：

```python
def _filter_items_for_section(
    items: List[Dict[str, Any]],
    section: str,
    *,
    risk_level: str = "",
    body_parts: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    ...
```

过滤优先级：

1. `status == "active"`
2. `section in report_sections`
3. 若提供 `risk_level`，优先保留 `risk_levels` 匹配项
4. 若提供 `body_parts`，优先保留部位匹配项
5. 按 `priority` 降序参与后续排序

### 打分建议

在当前关键词召回逻辑上增加一个简单重排分：

```text
总分 = 词项匹配分
     + report_sections 命中加权
     + risk_levels 命中加权
     + body_parts 命中加权
     + priority 权重
```

建议初始权重：

- `report_sections` 命中：`+5`
- `risk_levels` 命中：`+3`
- `body_parts` 命中：`+2`
- `priority`: `priority * 0.2`

## 数据结构设计

建议在 `generate_report_ai()` 返回结构中新增以下字段：

```json
{
  "section_queries": {
    "diagnosis": "...",
    "doctor_opinion": "...",
    "report_note": "...",
    "treatment_plan_text": "..."
  },
  "section_retrieval": {
    "diagnosis": {
      "context": "...",
      "items": [...],
      "citations": [...],
      "evidence_item_ids": ["KB-HT-002", "KB-HT-003"]
    },
    "doctor_opinion": {
      "context": "...",
      "items": [...],
      "citations": [...],
      "evidence_item_ids": ["KB-HT-006", "KB-HT-008"]
    },
    "report_note": {
      "context": "...",
      "items": [...],
      "citations": [...],
      "evidence_item_ids": ["KB-HT-001", "KB-HT-010"]
    },
    "treatment_plan_text": {
      "context": "...",
      "items": [...],
      "citations": [...],
      "evidence_item_ids": ["KB-HT-007", "KB-HT-009"]
    }
  }
}
```

兼容字段继续保留：

- `retrieved_context`
- `retrieved_items`
- `citations`
- `evidence_item_ids`

其中：

- `retrieved_context` = `merged.context`
- `retrieved_items` = `merged.items`
- `citations` = `merged.citations`
- `evidence_item_ids` = 合并后的唯一 ID 列表

## Python 接口签名建议

### 1. 查询构造

```python
def build_section_queries(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, str]:
    """Build retrieval query per report field."""
```

### 2. 单字段检索

```python
def _retrieve_context_for_section(
    section: str,
    query: str,
    *,
    top_k: int,
    record_id: str,
) -> Dict[str, Any]:
    """Retrieve only from KB items applicable to one report section."""
```

### 3. 多字段检索

```python
def retrieve_context_by_section(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    *,
    top_k_map: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Run retrieval for diagnosis/doctor_opinion/report_note/treatment_plan_text."""
```

### 4. 按字段构造 LLM 上下文

```python
def _build_llm_context_for_section(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    section: str,
    retrieved_context: str = "",
) -> str:
    """Build section-specific prompt context."""
```

## 返回结果设计

建议 `generate_report_ai()` 最终返回：

```json
{
  "model": "qwen3:1.7b",
  "diagnosis": "...",
  "doctor_opinion": "...",
  "report_note": "...",
  "treatment_plan_text": "...",
  "retrieved_context": "...",
  "retrieved_items": [...],
  "citations": [...],
  "evidence_item_ids": [...],
  "diagnosis_evidence_item_ids": [...],
  "plan_evidence_item_ids": [...],
  "section_queries": {...},
  "section_retrieval": {...}
}
```

## 在当前代码中的最小改造点

### `ingestion/app/llm_report.py`

需要改造：

1. `_load_kb_items()`
   - 保留结构化字段，而不只是 `id/title/content/tags/source`
2. `_build_retrieval_query()`
   - 保留旧函数，新增 `build_section_queries()`
3. `_retrieve_context()`
   - 保留旧函数，新增 `_retrieve_context_for_section()` 和 `retrieve_context_by_section()`
4. `_build_llm_context()`
   - 保留旧函数，新增 `_build_llm_context_for_section()`
5. `generate_report_ai()`
   - 从单次检索改为多字段检索

### `route/ingest.py`

当前回写逻辑基本可复用，只需补充透传：

- `section_queries`
- `section_retrieval`

如果这些字段是 `dict`，直接写入 `merged_report`。

## 推荐 top_k 配置

建议不要全字段统一 `top_k=5`。

初始配置：

```python
top_k_map = {
    "diagnosis": 4,
    "doctor_opinion": 5,
    "report_note": 3,
    "treatment_plan_text": 5,
}
```

理由：

- `report_note` 更偏规范性，少量高质量条目更好
- `doctor_opinion` 和 `treatment_plan_text` 通常需要更多安全边界与建议类条目

## 观测与调试

建议新增日志：

```text
[RAG-SECTION] record_id=... section=diagnosis query=... hits=...
[RAG-SECTION] record_id=... section=doctor_opinion refs=[...]
[RAG-SECTION] record_id=... section=treatment_plan_text refs=[...]
```

这样后续可以直接判断：

- 诊断字段是否误召回了治疗建议
- 治疗字段是否漏召回禁忌/转诊规则

## 迁移步骤

### Phase 1

只做检索层拆分，不改 LLM prompt 内容。

目标：

- 产出 `section_queries`
- 产出 `section_retrieval`
- 继续用合并上下文生成结果

### Phase 2

改成按字段上下文生成：

- `diagnosis` 用诊断上下文
- `doctor_opinion` 用医生意见上下文
- `report_note` 用报告说明上下文
- `treatment_plan_text` 用治疗建议上下文

### Phase 3

加入结构化过滤：

- 按 `risk_levels`
- 按 `body_parts`
- 按 `priority`

## 不建议的做法

- 不要继续把同一份 `retrieved_context` 直接喂给所有报告字段
- 不要只依赖 `tags` 做字段区分
- 不要先做复杂 reranker，再做字段化检索

先把“字段边界”做好，收益最大，改动最小。
