from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"
RAG_ENABLED = os.getenv("RAG_ENABLED", "1") != "0"
RAG_TOP_K = max(1, int(os.getenv("RAG_TOP_K", "5")))
RAG_KB_PATH = os.getenv(
    "RAG_KB_PATH",
    str(Path(__file__).resolve().parents[2] / "config" / "knowledge_base.jsonl"),
)

_KB_ITEMS_CACHE: Optional[List[Dict[str, Any]]] = None


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


def _build_retrieval_query(report: Dict[str, Any], emr: Dict[str, Any]) -> str:
    patient = report.get("patient") or emr.get("patient") or {}
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}
    regional = (analysis.get("regional_comparison") or {}) if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else []

    region_names = []
    if isinstance(abnormal_regions, list):
        region_names = [str(item.get("region") or "") for item in abnormal_regions if isinstance(item, dict)]

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
    return "\n".join(query_parts)


def _retrieve_context(query: str, top_k: int = RAG_TOP_K) -> Dict[str, Any]:
    if not RAG_ENABLED:
        return {"query": query, "items": [], "context": ""}

    items = _load_kb_items()
    if not items:
        return {"query": query, "items": [], "context": ""}

    q_tokens = set(_tokenize_text(query))
    if not q_tokens:
        return {"query": query, "items": [], "context": ""}

    scored: List[tuple[float, Dict[str, Any]]] = []
    for item in items:
        item_text = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("content") or ""),
                " ".join(_to_list_of_str(item.get("tags"))),
            ]
        )
        i_tokens = set(_tokenize_text(item_text))
        if not i_tokens:
            continue
        overlap = q_tokens.intersection(i_tokens)
        if not overlap:
            continue
        score = len(overlap) / max(1, len(q_tokens))
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [row[1] for row in scored[:top_k]]

    context_lines: List[str] = []
    for item in selected:
        context_lines.append(
            f"[{item['id']}] {item.get('title') or '-'}\n{item.get('content') or ''}"
        )

    return {
        "query": query,
        "items": selected,
        "context": "\n\n".join(context_lines),
    }


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
            "\n以下是检索到的医学知识条目（每条以[条目ID]开头）。"
            "请仅在有依据时引用，并在输出中给出依据条目ID：\n"
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


def _generate_llm_diagnosis_and_opinion(context: str) -> Dict[str, Any]:
    base_prompt = (
        context
        + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note, evidence_item_ids。"
        "每个字段输出 3-5 句中文，不少于 80 字，需包含风险等级与温度范围信息，"
        "其中 doctor_opinion 和 report_note 必须明确‘仅供参考’。"
        "evidence_item_ids 为字符串数组，填写你使用的依据条目ID（如 [\"KB-001\",\"KB-010\"]）。"
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
            context
            + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note, evidence_item_ids。"
            "请输出更详细的内容，每个字段不少于 120 字，分为 3-5 句，"
            "需包含风险等级、温度范围与建议要点，"
            "其中 doctor_opinion 和 report_note 必须包含‘仅供参考’。"
            "evidence_item_ids 为字符串数组，填写依据条目ID。"
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
        context
        + "以下为规则引擎生成的治疗方案要点，请返回严格JSON，包含字段：treatment_plan_text, evidence_item_ids。"
        "请生成精简但具体的中文说明（3-6句），"
        "需涵盖频次/疗程/关键部位，并标注‘仅供参考’：\n"
        + json.dumps(plan_summary, ensure_ascii=False)
    )
    text = _ollama_generate(prompt, temperature=0.3, max_tokens=700)
    data = _extract_json_block(text) or {}
    return {
        "treatment_plan_text": str(data.get("treatment_plan_text") or text or "").strip(),
        "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids")),
    }


def generate_report_ai(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, Any]:
    if not OLLAMA_ENABLED:
        return {}

    retrieval_query = _build_retrieval_query(report, emr)
    retrieval_result = _retrieve_context(retrieval_query)
    retrieved_context = str(retrieval_result.get("context") or "")
    context = _build_llm_context(report, emr, retrieved_context=retrieved_context)
    diag_payload = _generate_llm_diagnosis_and_opinion(context)
    plan_text = ""
    plan_evidence_ids: List[str] = []
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
        payload["diagnosis"] = diag_payload["diagnosis"]
    if diag_payload.get("doctor_opinion"):
        payload["doctor_opinion"] = diag_payload["doctor_opinion"]
    if diag_payload.get("report_note"):
        payload["report_note"] = diag_payload["report_note"]
    if plan_text:
        payload["treatment_plan_text"] = plan_text

    diagnosis_evidence_ids = _parse_evidence_ids(diag_payload.get("evidence_item_ids"))
    if diagnosis_evidence_ids:
        payload["diagnosis_evidence_item_ids"] = diagnosis_evidence_ids
    if plan_evidence_ids:
        payload["plan_evidence_item_ids"] = plan_evidence_ids

    merged_evidence_ids = sorted(set(diagnosis_evidence_ids + plan_evidence_ids))
    payload["evidence_item_ids"] = merged_evidence_ids

    return payload
