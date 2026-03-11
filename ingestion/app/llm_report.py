from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"
RAG_ENABLED = os.getenv("RAG_ENABLED", "1") != "0"
RAG_TOP_K = max(1, int(os.getenv("RAG_TOP_K", "5")))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0"))
RAG_VECTOR_ENABLED = os.getenv("RAG_VECTOR_ENABLED", "1") != "0"
RAG_VECTOR_KB_PATH = os.getenv(
    "RAG_VECTOR_KB_PATH",
    str(Path(__file__).resolve().parents[2] / "rag" / "kb" / "current"),
)
RAG_EMBED_PROVIDER = os.getenv("RAG_EMBED_PROVIDER", "ollama")
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "bge-m3:latest")
RAG_OPENAI_BASE_URL = os.getenv("RAG_OPENAI_BASE_URL")
RAG_OPENAI_API_KEY = os.getenv("RAG_OPENAI_API_KEY")
RAG_KB_PATH = os.getenv(
    "RAG_KB_PATH",
    str(Path(__file__).resolve().parents[2] / "config" / "knowledge_base.jsonl"),
)

_KB_ITEMS_CACHE: Optional[List[Dict[str, Any]]] = None
_VECTOR_KB_CACHE: Optional[Any] = None
_VECTOR_EMBEDDINGS: Any = None
_VECTOR_DISABLED_REASON: Optional[str] = None
_REF_PATTERN = re.compile(r"\[(\d+)\]")
_SYSTEM_PROMPT = (
    "你是医疗热成像评估助手。你只能基于提供的资料回答。"
    "必须在结论中使用编号引用（如[1]），不得编造，不确定就明确说明无法确认。"
)


def _short_text(value: str, limit: int = 160) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _extract_record_id(report: Dict[str, Any], emr: Dict[str, Any]) -> str:
    for container in (report, emr):
        if not isinstance(container, dict):
            continue
        value = str(container.get("record_id") or "").strip()
        if value:
            return value
    return "unknown"


def _import_top_level_rag_modules():
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    from rag.embeddings import build_embeddings
    from rag.kb_loader import load_kb

    return load_kb, build_embeddings

# Airport-inquiry uses a rule-first extraction strategy before LLM/tool routing.
# Reuse that idea here to stabilize KB retrieval against noisy free text.
_KEYWORD_RULES: Dict[str, List[str]] = {
    "body_part": [
        "颈", "肩", "肩背", "背", "腰", "腰背", "腹", "上腹", "下腹", "膝", "踝", "足", "手", "腕", "肘", "胸", "头", "面", "颈肩",
    ],
    "risk": ["低风险", "中风险", "高风险", "炎症", "疼痛", "应激", "循环", "供血", "温差", "异常", "复评"],
    "treatment": ["疗程", "频次", "干预", "理疗", "保暖", "复测", "随访", "医生意见", "治疗方案"],
}


def is_llm_enabled() -> bool:
    return OLLAMA_ENABLED


def _extract_json_block(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _ollama_generate(prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
    if not OLLAMA_ENABLED:
        return ""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
        result = json.loads(body)
        return str(result.get("response") or "").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        logging.error("Ollama generate error: %s: %s", type(exc).__name__, exc)
        logging.error("Model: %s, URL: %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
        return ""


def _to_list_of_str(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _load_kb_items() -> List[Dict[str, Any]]:
    global _KB_ITEMS_CACHE
    if _KB_ITEMS_CACHE is not None:
        return _KB_ITEMS_CACHE

    path = Path(RAG_KB_PATH)
    if not path.exists() or not path.is_file():
        _KB_ITEMS_CACHE = []
        return _KB_ITEMS_CACHE

    items: List[Dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else []
        else:
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue

        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id") or row.get("item_id") or "").strip()
            content = str(row.get("content") or row.get("text") or "").strip()
            if not item_id or not content:
                continue
            items.append(
                {
                    "id": item_id,
                    "title": str(row.get("title") or "").strip(),
                    "content": content,
                    "tags": _to_list_of_str(row.get("tags")),
                    "source": str(row.get("source") or "").strip(),
                }
            )
    except Exception as exc:
        logging.error("load kb items failed: %s", exc)

    _KB_ITEMS_CACHE = items
    return _KB_ITEMS_CACHE


def _tokenize_text(text: str) -> List[str]:
    if not text:
        return []
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_\-]+", lowered)
    cjk = re.findall(r"[\u4e00-\u9fff]{1,}", lowered)
    return [token for token in (latin + cjk) if token]


def _extract_rule_keywords(text: str) -> List[str]:
    if not text:
        return []
    matched: List[str] = []
    lowered = text.lower()
    for _, words in _KEYWORD_RULES.items():
        for word in words:
            if word and (word in text or word.lower() in lowered):
                matched.append(word)
    # keep order and deduplicate
    seen = set()
    result: List[str] = []
    for item in matched:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _build_retrieval_query(report: Dict[str, Any], emr: Dict[str, Any]) -> str:
    patient = report.get("patient") or emr.get("patient") or {}
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}
    regional = (analysis.get("regional_comparison") or {}) if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else []

    region_names = []
    if isinstance(abnormal_regions, list):
        for item in abnormal_regions:
            if not isinstance(item, dict):
                continue
            region = str(item.get("region") or "").strip()
            region_cn = str(item.get("region_cn") or "").strip()
            if region_cn and region:
                region_names.append(f"{region_cn}({region})")
            elif region_cn:
                region_names.append(region_cn)
            elif region:
                region_names.append(region)

    query_parts = [
        f"部位:{patient.get('body_part')}",
        f"性别:{patient.get('gender')}",
        f"年龄:{patient.get('age')}",
        f"风险:{analysis.get('risk_level') if isinstance(analysis, dict) else '-'}",
        f"最低温:{metrics.get('min_c')}",
        f"最高温:{metrics.get('max_c')}",
        f"平均温:{metrics.get('avg_c')}",
        "异常区域:" + ",".join(region_names),
    ]

    # Add deterministic medical keywords extracted from EMR narrative fields.
    emr_text = "\n".join(
        [
            str(emr.get("chief_complaint") or ""),
            str(emr.get("diagnosis") or ""),
            str(emr.get("doctor_opinion") or ""),
            str(emr.get("history") or ""),
        ]
    )
    keywords = _extract_rule_keywords(emr_text)
    if keywords:
        query_parts.append("规则关键词:" + ",".join(keywords))

    return "\n".join(query_parts)


def _load_vector_kb() -> Optional[Any]:
    global _VECTOR_KB_CACHE, _VECTOR_DISABLED_REASON
    if _VECTOR_KB_CACHE is not None:
        return _VECTOR_KB_CACHE
    if _VECTOR_DISABLED_REASON is not None:
        return None
    if not RAG_VECTOR_ENABLED:
        _VECTOR_DISABLED_REASON = "vector disabled"
        return None

    try:
        load_kb, _ = _import_top_level_rag_modules()

        _VECTOR_KB_CACHE = load_kb(RAG_VECTOR_KB_PATH)
        return _VECTOR_KB_CACHE
    except Exception as exc:
        _VECTOR_DISABLED_REASON = str(exc)
        logging.warning("vector kb unavailable: %s", exc)
        return None


def _load_vector_embeddings() -> Optional[Any]:
    global _VECTOR_EMBEDDINGS, _VECTOR_DISABLED_REASON
    if _VECTOR_EMBEDDINGS is not None:
        return _VECTOR_EMBEDDINGS
    if _VECTOR_DISABLED_REASON is not None and "vector disabled" in _VECTOR_DISABLED_REASON:
        return None

    try:
        _, build_embeddings = _import_top_level_rag_modules()

        base_url = OLLAMA_BASE_URL if RAG_EMBED_PROVIDER == "ollama" else RAG_OPENAI_BASE_URL
        _VECTOR_EMBEDDINGS = build_embeddings(
            provider=RAG_EMBED_PROVIDER,
            embed_model=RAG_EMBED_MODEL,
            base_url=base_url,
            api_key=RAG_OPENAI_API_KEY,
        )
        return _VECTOR_EMBEDDINGS
    except Exception as exc:
        _VECTOR_DISABLED_REASON = str(exc)
        logging.warning("vector embeddings unavailable: %s", exc)
        return None


def _retrieve_context_vector(query: str, top_k: int = RAG_TOP_K) -> Optional[Dict[str, Any]]:
    kb = _load_vector_kb()
    embeddings = _load_vector_embeddings()
    if kb is None or embeddings is None:
        return None

    try:
        import faiss
        import numpy as np

        vec = embeddings.embed_query(query)
        arr = np.array([vec], dtype="float32")
        faiss.normalize_L2(arr)
        scores, indices = kb.index.search(arr, top_k)
    except Exception as exc:
        logging.warning("vector retrieval failed: %s", exc)
        return None

    scores_list = scores[0].tolist()
    indices_list = indices[0].tolist()
    if scores_list and RAG_SCORE_THRESHOLD > 0 and scores_list[0] < RAG_SCORE_THRESHOLD:
        return {"query": query, "items": [], "citations": [], "context": ""}

    selected: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    context_lines: List[str] = []

    def _row_field(row: Any, name: str) -> Any:
        if isinstance(row, dict):
            return row.get(name)
        if hasattr(row, name):
            return getattr(row, name)
        return None

    rank = 0
    for idx, score in zip(indices_list, scores_list):
        if idx < 0:
            continue
        row = kb.chunks.get(int(idx))
        if row is None:
            continue
        rank += 1
        excerpt = str(_row_field(row, "excerpt_markdown") or _row_field(row, "text_for_embedding") or "").strip()
        if not excerpt:
            continue
        title_path = _row_field(row, "title_path")
        if isinstance(title_path, list):
            title_value = " > ".join(title_path)
        else:
            title_value = str(title_path or "")
        item = {
            "id": str(_row_field(row, "chunk_id") or f"VEC-{idx}"),
            "title": title_value,
            "content": excerpt,
            "source": str(_row_field(row, "file_path") or ""),
            "tags": [],
        }
        selected.append(item)
        citations.append(
            {
                "ref": rank,
                "id": item["id"],
                "title": item["title"],
                "source": item["source"],
                "score": float(score),
            }
        )
        context_lines.append(f"[{rank}] {item['title'] or '-'}\n{item['content']}")

    return {
        "query": query,
        "items": selected,
        "citations": citations,
        "context": "\n\n".join(context_lines),
    }


def _retrieve_context(query: str, top_k: int = RAG_TOP_K, record_id: str = "unknown") -> Dict[str, Any]:
    if not RAG_ENABLED:
        logging.info("[RAG] skipped record_id=%s: disabled (RAG_ENABLED=0)", record_id)
        return {"query": query, "items": [], "context": ""}

    vector_result = _retrieve_context_vector(query, top_k=top_k)
    if isinstance(vector_result, dict):
        items = vector_result.get("items") or []
        citations = vector_result.get("citations") or []
        logging.info(
            "[RAG] record_id=%s mode=vector query=%s hits=%d refs=%s",
            record_id,
            _short_text(query),
            len(items),
            [str(item.get("id") or "") for item in citations],
        )
        return vector_result

    items = _load_kb_items()
    if not items:
        return {"query": query, "items": [], "context": ""}

    q_tokens = set(_tokenize_text(query))
    if not q_tokens:
        return {"query": query, "items": [], "context": ""}

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for item in items:
        title_text = str(item.get("title") or "")
        tags_text = " ".join(_to_list_of_str(item.get("tags")))
        item_text = " ".join(
            [
                title_text,
                str(item.get("content") or ""),
                tags_text,
            ]
        )
        i_tokens = set(_tokenize_text(item_text))
        if not i_tokens:
            continue
        overlap = q_tokens.intersection(i_tokens)
        if not overlap:
            continue

        title_tokens = set(_tokenize_text(title_text))
        tag_tokens = set(_tokenize_text(tags_text))
        title_overlap = len(q_tokens.intersection(title_tokens)) / max(1, len(q_tokens))
        tag_overlap = len(q_tokens.intersection(tag_tokens)) / max(1, len(q_tokens))
        base_overlap = len(overlap) / max(1, len(q_tokens))
        score = base_overlap + (0.35 * title_overlap) + (0.25 * tag_overlap)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored and RAG_SCORE_THRESHOLD > 0 and scored[0][0] < RAG_SCORE_THRESHOLD:
        scored = []
    selected_pairs = scored[:top_k]
    selected = [row[1] for row in selected_pairs]

    citations: List[Dict[str, Any]] = []
    for rank, (score, item) in enumerate(selected_pairs, start=1):
        citations.append(
            {
                "ref": rank,
                "id": item.get("id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "score": score,
            }
        )

    context_lines: List[str] = []
    for rank, item in enumerate(selected, start=1):
        context_lines.append(
            f"[{rank}] {item.get('title') or '-'}\n{item.get('content') or ''}"
        )

    result = {
        "query": query,
        "items": selected,
        "citations": citations,
        "context": "\n\n".join(context_lines),
    }
    logging.info(
        "[RAG] record_id=%s mode=keyword query=%s hits=%d refs=%s",
        record_id,
        _short_text(query),
        len(selected),
        [str(item.get("id") or "") for item in citations],
    )
    return result


def _build_llm_context(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    retrieved_context: str = "",
) -> str:
    patient = report.get("patient") or emr.get("patient") or {}
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}
    risk_level = str(analysis.get("risk_level") or "-")
    summary = str(analysis.get("summary") or "-")
    abnormal_regions = []
    if isinstance(analysis, dict):
        abnormal_regions = (analysis.get("regional_comparison") or {}).get("abnormal_regions") or []
    body_part = patient.get("body_part") or "unknown"

    context = (
        "你是一名医疗热成像评估助手。请基于以下信息生成简洁、谨慎的中文内容。"
        "输出只需客观结论，避免夸大或绝对化表述。\n"
        f"患者信息：姓名={patient.get('name','-')} 性别={patient.get('gender','-')} 年龄={patient.get('age','-')} 部位={body_part}\n"
        f"风险等级：{risk_level}\n"
        f"温度摘要：{summary}\n"
        f"温度指标：min={metrics.get('min_c')} max={metrics.get('max_c')} avg={metrics.get('avg_c')}\n"
        f"异常区域：{abnormal_regions}\n"
    )
    if retrieved_context:
        context += (
            "\n以下是检索到的医学知识条目（每条以编号[1][2]...开头）。"
            "请仅在有依据时引用，并在输出中保留对应编号：\n"
            f"{retrieved_context}\n"
        )
    return context


def _parse_evidence_ids(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        ids = re.findall(r"[A-Za-z0-9_\-]+", value)
        return [item for item in ids if item]
    return []


def _strip_invalid_refs(answer: str, max_ref: int) -> str:
    def replace(match: re.Match[str]) -> str:
        num = int(match.group(1))
        return match.group(0) if num <= max_ref else ""

    return _REF_PATTERN.sub(replace, answer or "")


def _extract_ref_numbers(text: str) -> Set[int]:
    if not text:
        return set()
    return {int(item) for item in _REF_PATTERN.findall(text)}


def _resolve_ref_ids(text: str, citations: List[Dict[str, Any]]) -> List[str]:
    refs = _extract_ref_numbers(text)
    resolved: List[str] = []
    for num in sorted(refs):
        idx = num - 1
        if idx < 0 or idx >= len(citations):
            continue
        item_id = str(citations[idx].get("id") or "").strip()
        if item_id:
            resolved.append(item_id)
    return resolved


def _handle_common_query(question: str) -> Optional[str]:
    text = (question or "").strip()
    if any(keyword in text for keyword in ["今天几号", "今天几月几号", "今天是几号", "今天日期", "现在几号", "今日日期", "今天多少号"]):
        now = datetime.now()
        return f"今天是 {now.year}年{now.month}月{now.day}日。"
    if any(keyword in text for keyword in ["现在几点", "现在时间", "当前时间", "几点了"]):
        now = datetime.now()
        return f"现在时间是 {now.year}年{now.month}月{now.day}日 {now.hour}:{now.minute:02d}。"
    if "星期几" in text or "周几" in text:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return f"今天是 {now.year}年{now.month}月{now.day}日，{weekdays[now.weekday()]}。"
    return None


def _generate_llm_diagnosis_and_opinion(context: str) -> Dict[str, Any]:
    base_prompt = (
        _SYSTEM_PROMPT
        + "\n\n"
        + context
        + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note, evidence_item_ids。"
        "每个字段输出 3-5 句中文，不少于 80 字，需包含风险等级与温度范围信息，"
        "并在 diagnosis/doctor_opinion/report_note 中使用引用编号（如[1]）。"
        "其中 doctor_opinion 和 report_note 必须明确‘仅供参考’。"
        "evidence_item_ids 为字符串数组，可填写依据条目ID或引用编号（如 [\"KB-001\",\"[1]\"]）。"
    )
    text = _ollama_generate(base_prompt, temperature=0.2, max_tokens=900)
    data = _extract_json_block(text) or {}
    result = {
        "diagnosis": str(data.get("diagnosis") or "").strip(),
        "doctor_opinion": str(data.get("doctor_opinion") or "").strip(),
        "report_note": str(data.get("report_note") or "").strip(),
        "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids")),
    }

    def _too_short(value: str) -> bool:
        return len(value) < 80

    if any(_too_short(value) for value in result.values()):
        retry_prompt = (
            _SYSTEM_PROMPT
            + "\n\n"
            + context
            + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note, evidence_item_ids。"
            "请输出更详细的内容，每个字段不少于 120 字，分为 3-5 句，"
            "需包含风险等级、温度范围与建议要点，"
            "并在 diagnosis/doctor_opinion/report_note 中使用引用编号（如[1]）。"
            "其中 doctor_opinion 和 report_note 必须包含‘仅供参考’。"
            "evidence_item_ids 为字符串数组，可填写依据条目ID或引用编号。"
        )
        text = _ollama_generate(retry_prompt, temperature=0.2, max_tokens=1200)
        data = _extract_json_block(text) or {}
        result = {
            "diagnosis": str(data.get("diagnosis") or result["diagnosis"]).strip(),
            "doctor_opinion": str(data.get("doctor_opinion") or result["doctor_opinion"]).strip(),
            "report_note": str(data.get("report_note") or result["report_note"]).strip(),
            "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids") or result["evidence_item_ids"]),
        }

    return result


def _generate_llm_plan_text(context: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    plan_summary = {
        "intensity_level": plan.get("intensity_level"),
        "sessions": plan.get("sessions"),
        "frequency": plan.get("frequency"),
        "target_regions": plan.get("target_regions"),
        "acupoints": plan.get("acupoints"),
    }
    prompt = (
        _SYSTEM_PROMPT
        + "\n\n"
        + context
        + "以下为规则引擎生成的治疗方案要点，请返回严格JSON，包含字段：treatment_plan_text, evidence_item_ids。"
        "请生成精简但具体的中文说明（3-6句），"
        "需涵盖频次/疗程/关键部位，并标注‘仅供参考’，且使用引用编号（如[1]）：\n"
        + json.dumps(plan_summary, ensure_ascii=False)
    )
    text = _ollama_generate(prompt, temperature=0.3, max_tokens=700)
    data = _extract_json_block(text) or {}
    return {
        "treatment_plan_text": str(data.get("treatment_plan_text") or text or "").strip(),
        "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids")),
    }


def generate_report_ai(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, Any]:
    record_id = _extract_record_id(report, emr)

    if not OLLAMA_ENABLED:
        logging.info("[RAG] skipped record_id=%s: llm disabled (OLLAMA_ENABLED=0)", record_id)
        return {}

    retrieval_query = _build_retrieval_query(report, emr)
    logging.info(
        "[RAG] start record_id=%s enabled=%s vector_enabled=%s top_k=%s query=%s",
        record_id,
        RAG_ENABLED,
        RAG_VECTOR_ENABLED,
        RAG_TOP_K,
        _short_text(retrieval_query),
    )
    common_answer = _handle_common_query(retrieval_query)
    if common_answer:
        logging.info("[RAG] short-circuit record_id=%s: common query matched, skip retrieval", record_id)
        return {
            "model": OLLAMA_MODEL,
            "retrieved_context": "",
            "retrieved_items": [],
            "report_note": common_answer,
            "evidence_item_ids": [],
        }

    retrieval_result = _retrieve_context(retrieval_query, record_id=record_id)
    retrieved_context = str(retrieval_result.get("context") or "")
    citations = retrieval_result.get("citations") or []
    if not retrieval_result.get("items"):
        logging.info("[RAG] completed record_id=%s with 0 hits", record_id)
        return {
            "model": OLLAMA_MODEL,
            "retrieved_context": "",
            "retrieved_items": [],
            "report_note": "知识库未找到依据，无法确认。",
            "evidence_item_ids": [],
        }

    logging.info(
        "[RAG] completed record_id=%s hits=%d refs=%s",
        record_id,
        len(retrieval_result.get("items") or []),
        [str(item.get("id") or "") for item in citations],
    )

    context = _build_llm_context(report, emr, retrieved_context=retrieved_context)
    diag_payload = _generate_llm_diagnosis_and_opinion(context)
    plan_text = ""
    plan_evidence_ids: List[str] = []
    plan_payload: Dict[str, Any] = {}
    plan = report.get("treatment_plan") or {}
    if isinstance(plan, dict):
        plan_payload = _generate_llm_plan_text(context, plan)
        plan_text = str(plan_payload.get("treatment_plan_text") or "").strip()
        plan_evidence_ids = _parse_evidence_ids(plan_payload.get("evidence_item_ids"))

    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "retrieved_context": retrieved_context,
        "retrieved_items": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "tags": item.get("tags") or [],
            }
            for item in (retrieval_result.get("items") or [])
        ],
    }
    if diag_payload.get("diagnosis"):
        payload["diagnosis"] = _strip_invalid_refs(str(diag_payload["diagnosis"]), len(citations))
    if diag_payload.get("doctor_opinion"):
        payload["doctor_opinion"] = _strip_invalid_refs(str(diag_payload["doctor_opinion"]), len(citations))
    if diag_payload.get("report_note"):
        payload["report_note"] = _strip_invalid_refs(str(diag_payload["report_note"]), len(citations))
    if plan_text:
        payload["treatment_plan_text"] = _strip_invalid_refs(plan_text, len(citations))

    diagnosis_evidence_ids = _parse_evidence_ids(diag_payload.get("evidence_item_ids"))
    diagnosis_evidence_ids.extend(
        _resolve_ref_ids(
            "\n".join(
                [
                    str(payload.get("diagnosis") or ""),
                    str(payload.get("doctor_opinion") or ""),
                    str(payload.get("report_note") or ""),
                    json.dumps(diag_payload.get("evidence_item_ids") or [], ensure_ascii=False),
                ]
            ),
            citations,
        )
    )
    if diagnosis_evidence_ids:
        payload["diagnosis_evidence_item_ids"] = sorted(set(diagnosis_evidence_ids))

    plan_evidence_ids.extend(
        _resolve_ref_ids(
            "\n".join(
                [
                    str(payload.get("treatment_plan_text") or ""),
                    json.dumps(plan_payload.get("evidence_item_ids") or [], ensure_ascii=False),
                ]
            ),
            citations,
        )
    )
    if plan_evidence_ids:
        payload["plan_evidence_item_ids"] = sorted(set(plan_evidence_ids))

    merged_evidence_ids = sorted(set(diagnosis_evidence_ids + plan_evidence_ids))
    payload["evidence_item_ids"] = merged_evidence_ids
    payload["citations"] = citations

    return payload
