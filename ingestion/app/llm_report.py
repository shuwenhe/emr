from __future__ import annotations

import ast
import json
import logging
import os
import re
import socket
import sys
import time
from datetime import datetime
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _env_int(name: str, default: int, *, min_value: Optional[int] = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw is not None else default
    except Exception:
        value = default
    if min_value is not None:
        return max(min_value, value)
    return value

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"
OLLAMA_TIMEOUT_SEC = _env_int("OLLAMA_TIMEOUT_SEC", 60, min_value=5)
OLLAMA_MAX_RETRIES = _env_int("OLLAMA_MAX_RETRIES", 2, min_value=0)
OLLAMA_HEALTHCHECK_TIMEOUT_SEC = _env_int("OLLAMA_HEALTHCHECK_TIMEOUT_SEC", 2, min_value=1)
OLLAMA_UNAVAILABLE_COOLDOWN_SEC = _env_int("OLLAMA_UNAVAILABLE_COOLDOWN_SEC", 30, min_value=1)
OLLAMA_SECTION_WORKERS = _env_int("OLLAMA_SECTION_WORKERS", 2, min_value=1)
RAG_ENABLED = os.getenv("RAG_ENABLED", "1") != "0"
RAG_TOP_K = _env_int("RAG_TOP_K", 5, min_value=1)
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0"))
RAG_CONTEXT_ITEM_MAX_CHARS = _env_int("RAG_CONTEXT_ITEM_MAX_CHARS", 260, min_value=120)
RAG_VECTOR_ENABLED = os.getenv("RAG_VECTOR_ENABLED", "1") != "0"
RAG_VECTOR_LOAD_RETRIES = _env_int("RAG_VECTOR_LOAD_RETRIES", 5, min_value=0)
RAG_VECTOR_LOAD_RETRY_DELAY_SEC = max(0.1, float(os.getenv("RAG_VECTOR_LOAD_RETRY_DELAY_SEC", "0.5")))
RAG_VECTOR_KB_PATH = os.getenv(
    "RAG_VECTOR_KB_PATH",
    str(Path(__file__).resolve().parents[2] / "rag" / "kb" / "current_partial"),
)
RAG_EMBED_PROVIDER = os.getenv("RAG_EMBED_PROVIDER", "ollama")
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "bge-m3:latest")
RAG_OPENAI_BASE_URL = os.getenv("RAG_OPENAI_BASE_URL")
RAG_OPENAI_API_KEY = os.getenv("RAG_OPENAI_API_KEY")
RAG_KB_PATH = os.getenv(
    "RAG_KB_PATH",
    str(Path(__file__).resolve().parents[2] / "rag" / "kb" / "knowledge_base.jsonl"),
)

_KB_ITEMS_CACHE: Optional[List[Dict[str, Any]]] = None
_KB_ITEMS_MTIME: Optional[float] = None
_VECTOR_KB_CACHE: Optional[Any] = None
_VECTOR_KB_MTIME: Optional[float] = None
_VECTOR_EMBEDDINGS: Any = None
_VECTOR_DISABLED_REASON: Optional[str] = None
_RAG_CONFIG_LOGGED = False
_OLLAMA_UNAVAILABLE_UNTIL_TS = 0.0
_OLLAMA_UNAVAILABLE_LOGGED_TS = 0.0
_REF_PATTERN = re.compile(r"\[(\d+)\]")
_ABSOLUTE_DATE_PATTERN = re.compile(r"\b\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?\b")
_SYSTEM_PROMPT = (
    "你是医疗热成像评估助手。你只能基于提供的资料回答。"
    "必须在结论中使用编号引用（如[1]），不得编造，不确定就明确说明无法确认。"
)


def _short_text(value: str, limit: int = 160) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _truncate_context_item(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= RAG_CONTEXT_ITEM_MAX_CHARS:
        return text
    return text[:RAG_CONTEXT_ITEM_MAX_CHARS] + "..."


def _extract_record_id(report: Dict[str, Any], emr: Dict[str, Any]) -> str:
    for container in (report, emr):
        if not isinstance(container, dict):
            continue
        value = str(container.get("record_id") or "").strip()
        if value:
            return value
    return "unknown"


def _flatten_text_items(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items: List[str] = []
        for item in value:
            items.extend(_flatten_text_items(item))
        return items
    text = str(value).strip()
    return [text] if text else []


def _normalize_generated_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(_flatten_text_items(value))

    text = str(value or "").strip()
    if not text:
        return ""

    if text[:1] in "[(" and text[-1:] in "])":
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            parsed = None
        if isinstance(parsed, (list, tuple)):
            items = _flatten_text_items(parsed)
            if items:
                return "\n".join(items)

    return text


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
_REPORT_SECTIONS = ("diagnosis", "doctor_opinion", "report_note", "treatment_plan_text", "health_advice")
RAG_TOP_K_DIAGNOSIS = _env_int("RAG_TOP_K_DIAGNOSIS", 3, min_value=1)
RAG_TOP_K_DOCTOR_OPINION = _env_int("RAG_TOP_K_DOCTOR_OPINION", 3, min_value=1)
RAG_TOP_K_REPORT_NOTE = _env_int("RAG_TOP_K_REPORT_NOTE", 2, min_value=1)
RAG_TOP_K_TREATMENT_PLAN = _env_int("RAG_TOP_K_TREATMENT_PLAN", 3, min_value=1)
RAG_TOP_K_HEALTH_ADVICE = _env_int("RAG_TOP_K_HEALTH_ADVICE", 4, min_value=1)
_SECTION_TOP_K = {
    "diagnosis": RAG_TOP_K_DIAGNOSIS,
    "doctor_opinion": RAG_TOP_K_DOCTOR_OPINION,
    "report_note": RAG_TOP_K_REPORT_NOTE,
    "treatment_plan_text": RAG_TOP_K_TREATMENT_PLAN,
    "health_advice": RAG_TOP_K_HEALTH_ADVICE,
}
_SECTION_ALLOWED_CATEGORIES: Dict[str, Set[str]] = {
    "diagnosis": {"report_template", "interpretation_symmetry", "interpretation_hotspot"},
    "doctor_opinion": {"report_template", "follow_up_rule", "contraindication", "safety_rule"},
    "report_note": {"report_template", "sop_preparation", "contraindication", "safety_rule"},
    "treatment_plan_text": {"treatment_guideline", "follow_up_rule", "contraindication"},
    "health_advice": {"follow_up_rule", "treatment_guideline", "contraindication"},
}
_RISK_ALIASES = {
    "low": {"low", "低", "低风险"},
    "medium": {"medium", "mid", "中", "中风险"},
    "high": {"high", "高", "高风险"},
}
_BODY_PART_ALIASES = {
    "颈肩": {"颈肩", "颈", "肩", "肩背"},
    "腰背": {"腰背", "腰", "背"},
    "四肢": {"四肢", "上肢", "下肢", "手", "足", "腕", "肘", "踝"},
    "膝关节": {"膝", "膝关节"},
    "腹部": {"腹", "腹部", "上腹", "下腹"},
    "胸部": {"胸", "胸部"},
    "头面部": {"头", "面", "头面", "头面部"},
}


def is_llm_enabled() -> bool:
    return OLLAMA_ENABLED


def _log_rag_runtime_config_once() -> None:
    global _RAG_CONFIG_LOGGED
    if _RAG_CONFIG_LOGGED:
        return
    _RAG_CONFIG_LOGGED = True
    logging.info(
        "[RAG-CONFIG] enabled=%s vector_enabled=%s provider=%s embed_model=%s top_k=%s "
        "score_threshold=%s context_item_max_chars=%s section_workers=%s section_top_k=%s kb_path=%s vector_kb_path=%s",
        RAG_ENABLED,
        RAG_VECTOR_ENABLED,
        RAG_EMBED_PROVIDER,
        RAG_EMBED_MODEL,
        RAG_TOP_K,
        RAG_SCORE_THRESHOLD,
        RAG_CONTEXT_ITEM_MAX_CHARS,
        OLLAMA_SECTION_WORKERS,
        _SECTION_TOP_K,
        RAG_KB_PATH,
        RAG_VECTOR_KB_PATH,
    )


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


def _ollama_healthcheck() -> bool:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=OLLAMA_HEALTHCHECK_TIMEOUT_SEC) as response:
        return int(getattr(response, "status", 200) or 200) < 500


def _mark_ollama_unavailable(err: Exception) -> None:
    global _OLLAMA_UNAVAILABLE_UNTIL_TS, _OLLAMA_UNAVAILABLE_LOGGED_TS
    now = time.time()
    _OLLAMA_UNAVAILABLE_UNTIL_TS = now + OLLAMA_UNAVAILABLE_COOLDOWN_SEC
    # Log once per cooldown window to avoid noisy duplicate errors from parallel sections.
    if now >= _OLLAMA_UNAVAILABLE_LOGGED_TS:
        logging.warning(
            "Ollama unavailable, skip LLM calls for %ss model=%s base_url=%s err=%s",
            OLLAMA_UNAVAILABLE_COOLDOWN_SEC,
            OLLAMA_MODEL,
            OLLAMA_BASE_URL,
            err,
        )
        _OLLAMA_UNAVAILABLE_LOGGED_TS = _OLLAMA_UNAVAILABLE_UNTIL_TS


def _ollama_available() -> bool:
    if not OLLAMA_ENABLED:
        return False

    now = time.time()
    if now < _OLLAMA_UNAVAILABLE_UNTIL_TS:
        return False

    try:
        return _ollama_healthcheck()
    except Exception as exc:
        _mark_ollama_unavailable(exc)
        return False


def _ollama_generate(prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
    if not OLLAMA_ENABLED:
        return ""
    if not _ollama_available():
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
    delay = 0.8
    last_exc: Optional[Exception] = None
    for attempt in range(OLLAMA_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SEC) as response:
                body = response.read().decode("utf-8")
            result = json.loads(body)
            return str(result.get("response") or "").strip()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < OLLAMA_MAX_RETRIES:
                logging.warning(
                    "Ollama generate retrying attempt=%d/%d timeout=%ss model=%s err=%s",
                    attempt + 1,
                    OLLAMA_MAX_RETRIES,
                    OLLAMA_TIMEOUT_SEC,
                    OLLAMA_MODEL,
                    exc,
                )
                time.sleep(delay)
                delay = min(delay * 2.0, 5.0)
                continue

    if isinstance(last_exc, Exception):
        _mark_ollama_unavailable(last_exc)

    if last_exc is not None:
        logging.error("Ollama generate error: %s: %s", type(last_exc).__name__, last_exc)
    logging.error(
        "Model: %s, URL: %s, timeout=%ss, retries=%s",
        OLLAMA_MODEL,
        OLLAMA_BASE_URL,
        OLLAMA_TIMEOUT_SEC,
        OLLAMA_MAX_RETRIES,
    )
    return ""


def _to_list_of_str(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _load_kb_items() -> List[Dict[str, Any]]:
    global _KB_ITEMS_CACHE, _KB_ITEMS_MTIME
    path = Path(RAG_KB_PATH)
    try:
        current_mtime = path.stat().st_mtime if path.exists() else None
    except OSError:
        current_mtime = None
    if _KB_ITEMS_CACHE is not None and current_mtime == _KB_ITEMS_MTIME:
        return _KB_ITEMS_CACHE
    # File changed or first load — invalidate cache
    _KB_ITEMS_CACHE = None
    _KB_ITEMS_MTIME = current_mtime
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
                    "category": str(row.get("category") or "").strip(),
                    "report_sections": _to_list_of_str(row.get("report_sections")),
                    "priority": int(row.get("priority") or 0),
                    "status": str(row.get("status") or "active").strip() or "active",
                    "risk_levels": _to_list_of_str(row.get("risk_levels")),
                    "body_parts": _to_list_of_str(row.get("body_parts")),
                    "retrieval_hints": _to_list_of_str(row.get("retrieval_hints")),
                }
            )
    except Exception as exc:
        logging.error("load kb items failed: %s", exc)

    _KB_ITEMS_CACHE = items
    # mtime already set before load; reaffirm after successful load
    _KB_ITEMS_MTIME = current_mtime
    return _KB_ITEMS_CACHE


def _tokenize_text(text: str) -> List[str]:
    if not text:
        return []
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_\-]+", lowered)
    cjk = re.findall(r"[\u4e00-\u9fff]{1,}", lowered)
    return [token for token in (latin + cjk) if token]


def _normalize_risk_level(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for canonical, aliases in _RISK_ALIASES.items():
        if text in aliases:
            return canonical
    return text


def _expand_body_part_aliases(values: List[str]) -> Set[str]:
    expanded: Set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        expanded.add(text)
        for canonical, aliases in _BODY_PART_ALIASES.items():
            if text == canonical or text in aliases or any(alias in text or text in alias for alias in aliases):
                expanded.add(canonical)
                expanded.update(aliases)
    return expanded


def _body_part_matches(query_body_parts: List[str], item_body_parts: List[str]) -> bool:
    if not query_body_parts or not item_body_parts:
        return False
    query_expanded = _expand_body_part_aliases(query_body_parts)
    item_expanded = _expand_body_part_aliases(item_body_parts)
    if query_expanded.intersection(item_expanded):
        return True
    return any(q in i or i in q for q in query_expanded for i in item_expanded)


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


def _extract_report_features(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, Any]:
    patient = report.get("patient") or emr.get("patient") or {}
    analysis = report.get("analysis") or {}
    regional = (analysis.get("regional_comparison") or {}) if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else []

    body_parts: List[str] = []
    patient_body_part = str(patient.get("body_part") or "").strip()
    if patient_body_part and patient_body_part not in {"全身", "全身扫描", "全身检查"}:
        body_parts.append(patient_body_part)
    if isinstance(abnormal_regions, list):
        for item in abnormal_regions:
            if not isinstance(item, dict):
                continue
            for key in ("region_cn", "region"):
                value = str(item.get(key) or "").strip()
                if value and value not in body_parts:
                    body_parts.append(value)

    if not body_parts:
        # Fallback for generic records (e.g. body_part=全身): infer from EMR narratives.
        emr_text = "\n".join(
            [
                str(emr.get("chief_complaint") or ""),
                str(emr.get("diagnosis") or ""),
                str(emr.get("doctor_opinion") or ""),
                str(emr.get("history") or ""),
            ]
        )
        for canonical, aliases in _BODY_PART_ALIASES.items():
            if canonical in emr_text or any(alias in emr_text for alias in aliases):
                if canonical not in body_parts:
                    body_parts.append(canonical)

    risk_level = _normalize_risk_level(str(analysis.get("risk_level") or "").strip())
    return {
        "body_parts": body_parts,
        "risk_level": risk_level,
    }


def build_section_queries(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, str]:
    base_query = _build_retrieval_query(report, emr)
    features = _extract_report_features(report, emr)
    body_parts = ",".join(features["body_parts"]) if features["body_parts"] else ""
    risk_level = features["risk_level"]
    body_hint = f"部位:{body_parts}" if body_parts else ""
    risk_hint = f"风险:{risk_level}" if risk_level else ""

    def _join(parts: List[str]) -> str:
        return "\n".join([part for part in parts if part])

    return {
        "diagnosis": _join([base_query, body_hint, risk_hint, "判读原则", "温差", "异常区域", "风险分层"]),
        "doctor_opinion": _join([base_query, body_hint, risk_hint, "医生意见", "谨慎解释", "复评建议", "转诊提醒"]),
        "report_note": _join([base_query, body_hint, "检查准备", "报告说明", "仅供参考", "适用边界"]),
        "treatment_plan_text": _join([base_query, body_hint, risk_hint, "治疗方案", "疗程频次", "复评", "禁忌"]),
        "health_advice": _join([base_query, body_hint, risk_hint, "保健建议", "居家护理", "作息", "饮食", "运动", "复评"]),
    }


def _vector_kb_index_mtime(kb_dir: str) -> Optional[float]:
    """Return mtime of index.faiss inside kb_dir (follows symlinks)."""
    try:
        p = Path(kb_dir).resolve() / "index.faiss"
        return p.stat().st_mtime if p.exists() else None
    except OSError:
        return None


def _load_vector_kb() -> Optional[Any]:
    global _VECTOR_KB_CACHE, _VECTOR_KB_MTIME, _VECTOR_DISABLED_REASON
    if _VECTOR_DISABLED_REASON is not None and _VECTOR_DISABLED_REASON == "vector disabled":
        return None
    if not RAG_VECTOR_ENABLED:
        _VECTOR_DISABLED_REASON = "vector disabled"
        return None

    # Check if the on-disk KB has been updated since last load
    primary_candidate = str(RAG_VECTOR_KB_PATH).strip()
    project_root = Path(__file__).resolve().parents[2]
    fallback_partial = str(project_root / "rag" / "kb" / "current_partial")
    check_dir = primary_candidate or fallback_partial
    current_mtime = _vector_kb_index_mtime(check_dir)
    if _VECTOR_KB_CACHE is not None and current_mtime == _VECTOR_KB_MTIME:
        return _VECTOR_KB_CACHE
    if current_mtime != _VECTOR_KB_MTIME and _VECTOR_KB_CACHE is not None:
        logging.info("vector kb on-disk change detected, reloading (old_mtime=%s new_mtime=%s)", _VECTOR_KB_MTIME, current_mtime)
        _VECTOR_KB_CACHE = None
        _VECTOR_DISABLED_REASON = None
    if _VECTOR_DISABLED_REASON is not None:
        return None

    try:
        load_kb, _ = _import_top_level_rag_modules()
        candidates: List[str] = []
        primary = primary_candidate
        if primary:
            candidates.append(primary)

        project_root = Path(__file__).resolve().parents[2]
        fallback_partial = str(project_root / "rag" / "kb" / "current_partial")
        if fallback_partial not in candidates:
            candidates.append(fallback_partial)

        last_exc: Optional[Exception] = None
        for candidate in candidates:
            for attempt in range(RAG_VECTOR_LOAD_RETRIES + 1):
                try:
                    _VECTOR_KB_CACHE = load_kb(candidate)
                    _VECTOR_KB_MTIME = _vector_kb_index_mtime(candidate)
                    if candidate != primary:
                        logging.warning("vector kb fallback activated: %s", candidate)
                    return _VECTOR_KB_CACHE
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt >= RAG_VECTOR_LOAD_RETRIES:
                        break
                    logging.warning(
                        "vector kb load retrying: candidate=%s attempt=%d/%d err=%s",
                        candidate,
                        attempt + 1,
                        RAG_VECTOR_LOAD_RETRIES,
                        exc,
                    )
                    time.sleep(RAG_VECTOR_LOAD_RETRY_DELAY_SEC)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("vector kb candidates are empty")
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
        context_lines.append(f"[{rank}] {item['title'] or '-'}\n{_truncate_context_item(item['content'])}")

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


def _filter_items_for_section(
    items: List[Dict[str, Any]],
    section: str,
    *,
    risk_level: str = "",
    body_parts: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    body_parts = [part for part in (body_parts or []) if part]
    selected: List[Dict[str, Any]] = []
    for item in items:
        if str(item.get("status") or "active").lower() != "active":
            continue
        report_sections = _to_list_of_str(item.get("report_sections"))
        if report_sections and section not in report_sections:
            continue
        selected.append(item)
    allowed_categories = _SECTION_ALLOWED_CATEGORIES.get(section)
    if allowed_categories:
        scoped = [
            item
            for item in selected
            if str(item.get("category") or "").strip().lower() in allowed_categories
        ]
        if scoped:
            selected = scoped
    if not selected:
        return selected

    def risk_match(item: Dict[str, Any]) -> bool:
        item_risk_levels = [_normalize_risk_level(level) for level in _to_list_of_str(item.get("risk_levels"))]
        if not risk_level or not item_risk_levels:
            return False
        return risk_level in item_risk_levels

    def body_match(item: Dict[str, Any]) -> bool:
        item_body_parts = _to_list_of_str(item.get("body_parts"))
        if not body_parts or not item_body_parts:
            return False
        return _body_part_matches(body_parts, item_body_parts)

    strict = [item for item in selected if risk_match(item) and body_match(item)]
    if strict:
        return strict

    risk_only = [item for item in selected if risk_match(item)]
    body_only = [item for item in selected if body_match(item)]
    if risk_only and body_only:
        combined_ids = {str(item.get("id") or "") for item in risk_only}
        merged = risk_only + [item for item in body_only if str(item.get("id") or "") not in combined_ids]
        return merged
    if risk_only:
        return risk_only
    if body_only:
        return body_only
    return selected


def _score_section_item(
    item: Dict[str, Any],
    q_tokens: Set[str],
    *,
    section: str = "",
    risk_level: str = "",
    body_parts: Optional[List[str]] = None,
) -> float:
    title_text = str(item.get("title") or "")
    tags_text = " ".join(_to_list_of_str(item.get("tags")))
    hints_text = " ".join(_to_list_of_str(item.get("retrieval_hints")))
    item_text = " ".join([title_text, str(item.get("content") or ""), tags_text, hints_text])
    i_tokens = set(_tokenize_text(item_text))
    if not i_tokens:
        return 0.0
    overlap = q_tokens.intersection(i_tokens)
    if not overlap and section != "treatment_plan_text":
        return 0.0

    title_tokens = set(_tokenize_text(title_text))
    tag_tokens = set(_tokenize_text(tags_text))
    hint_tokens = set(_tokenize_text(hints_text))
    score = 0.0
    if overlap:
        base_overlap = len(overlap) / max(1, len(q_tokens))
        title_overlap = len(q_tokens.intersection(title_tokens)) / max(1, len(q_tokens))
        tag_overlap = len(q_tokens.intersection(tag_tokens)) / max(1, len(q_tokens))
        hint_overlap = len(q_tokens.intersection(hint_tokens)) / max(1, len(q_tokens))
        score = base_overlap + (0.35 * title_overlap) + (0.25 * tag_overlap) + (0.2 * hint_overlap)

    item_risk_levels = [_normalize_risk_level(level) for level in _to_list_of_str(item.get("risk_levels"))]
    if risk_level and item_risk_levels and risk_level in item_risk_levels:
        score += 4.0

    item_body_parts = _to_list_of_str(item.get("body_parts"))
    if body_parts and item_body_parts:
        if _body_part_matches(body_parts, item_body_parts):
            score += 3.0

    report_sections = _to_list_of_str(item.get("report_sections"))
    if report_sections:
        score += 0.8

    # Prefer case treatment snippets for treatment-plan generation.
    if section == "treatment_plan_text":
        item_id = str(item.get("id") or "")
        title_text_lower = title_text.lower()
        if "-C" in item_id or "病例" in title_text_lower:
            score += 1.2

    score += float(item.get("priority") or 0) * 0.5
    return score


def _is_case_treatment_item(item: Dict[str, Any]) -> bool:
    item_id = str(item.get("id") or "")
    title = str(item.get("title") or "")
    source = str(item.get("source") or "")
    category = str(item.get("category") or "").strip().lower()
    if category != "treatment_guideline":
        return False
    if "-C" in item_id:
        return True
    if "病例" in title or "病例" in source:
        return True
    return False


def _retrieve_context_for_section(
    section: str,
    query: str,
    *,
    top_k: int,
    record_id: str,
    risk_level: str = "",
    body_parts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not RAG_ENABLED:
        return {"query": query, "items": [], "citations": [], "context": "", "evidence_item_ids": []}

    items = _filter_items_for_section(
        _load_kb_items(),
        section,
        risk_level=risk_level,
        body_parts=body_parts,
    )
    q_tokens = set(_tokenize_text(query))
    if not items or not q_tokens:
        return {"query": query, "items": [], "citations": [], "context": "", "evidence_item_ids": []}

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for item in items:
        score = _score_section_item(
            item,
            q_tokens,
            section=section,
            risk_level=risk_level,
            body_parts=body_parts,
        )
        if score > 0:
            scored.append((score, item))
    scored.sort(
        key=lambda pair: (
            pair[0],
            float(pair[1].get("priority") or 0),
            len(_to_list_of_str(pair[1].get("report_sections"))),
        ),
        reverse=True,
    )
    selected_pairs = scored[:top_k]

    # Fallback: for treatment plan generation, enforce at least one case-based
    # treatment item in the retrieved set when such items are available.
    if section == "treatment_plan_text" and selected_pairs:
        has_case_item = any(_is_case_treatment_item(item) for _, item in selected_pairs)
        if not has_case_item:
            candidate_pairs = [(score, item) for score, item in scored if _is_case_treatment_item(item)]
            if candidate_pairs:
                candidate_score, candidate_item = candidate_pairs[0]
                existing_ids = {str(item.get("id") or "") for _, item in selected_pairs}
                if str(candidate_item.get("id") or "") not in existing_ids:
                    if len(selected_pairs) < top_k:
                        selected_pairs.append((candidate_score, candidate_item))
                    else:
                        selected_pairs[-1] = (candidate_score, candidate_item)
                    selected_pairs.sort(
                        key=lambda pair: (
                            pair[0],
                            float(pair[1].get("priority") or 0),
                            len(_to_list_of_str(pair[1].get("report_sections"))),
                        ),
                        reverse=True,
                    )
    selected = [row[1] for row in selected_pairs]
    citations: List[Dict[str, Any]] = []
    context_lines: List[str] = []
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
        context_lines.append(f"[{rank}] {item.get('title') or '-'}\n{_truncate_context_item(item.get('content') or '')}")

    result = {
        "query": query,
        "items": selected,
        "citations": citations,
        "context": "\n\n".join(context_lines),
        "evidence_item_ids": [str(item.get("id") or "") for item in selected if str(item.get("id") or "").strip()],
    }
    logging.info(
        "[RAG-SECTION] record_id=%s section=%s hits=%d refs=%s query=%s",
        record_id,
        section,
        len(selected),
        result["evidence_item_ids"],
        _short_text(query),
    )
    return result


def retrieve_context_by_section(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    *,
    top_k_map: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    record_id = _extract_record_id(report, emr)
    queries = build_section_queries(report, emr)
    features = _extract_report_features(report, emr)
    top_k_map = {**_SECTION_TOP_K, **(top_k_map or {})}
    sections: Dict[str, Any] = {}

    merged_by_id: Dict[str, Dict[str, Any]] = {}
    merged_citations: List[Dict[str, Any]] = []
    for section in _REPORT_SECTIONS:
        section_result = _retrieve_context_for_section(
            section,
            queries.get(section, ""),
            top_k=int(top_k_map.get(section, RAG_TOP_K)),
            record_id=record_id,
            risk_level=features["risk_level"],
            body_parts=features["body_parts"],
        )
        sections[section] = section_result
        for item in section_result.get("items") or []:
            item_id = str(item.get("id") or "").strip()
            if item_id and item_id not in merged_by_id:
                merged_by_id[item_id] = item
        for citation in section_result.get("citations") or []:
            item_id = str(citation.get("id") or "").strip()
            if item_id and all(str(existing.get("id") or "") != item_id for existing in merged_citations):
                merged_citations.append(citation)

    merged_items = list(merged_by_id.values())
    merged_context_lines = []
    for rank, item in enumerate(merged_items, start=1):
        merged_context_lines.append(f"[{rank}] {item.get('title') or '-'}\n{_truncate_context_item(item.get('content') or '')}")
    merged = {
        "items": merged_items,
        "citations": merged_citations,
        "context": "\n\n".join(merged_context_lines),
        "evidence_item_ids": [str(item.get("id") or "") for item in merged_items if str(item.get("id") or "").strip()],
    }
    return {
        "section_queries": queries,
        "sections": sections,
        "merged": merged,
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
            "\n以下是检索到的医学知识条目（每条以编号[1][2]...开头）。"
            "请仅在有依据时引用，并在输出中保留对应编号：\n"
            f"{retrieved_context}\n"
        )
    return context


def _build_llm_context_for_section(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    section: str,
    retrieved_context: str = "",
) -> str:
    section_labels = {
        "diagnosis": "诊断结论",
        "doctor_opinion": "医生意见",
        "report_note": "报告说明",
        "treatment_plan_text": "治疗建议",
        "health_advice": "保健建议",
    }
    context = _build_llm_context(report, emr, retrieved_context=retrieved_context)
    return context + f"\n当前任务字段：{section_labels.get(section, section)}\n"


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


def _normalize_followup_date_text(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value

    # For safety, replace any absolute calendar date in generated narrative text
    # with a relative follow-up window to avoid stale/hallucinated years.
    normalized = _ABSOLUTE_DATE_PATTERN.sub("7-14天内", value)
    normalized = normalized.replace("复评于7-14天内", "建议7-14天内复评")
    normalized = normalized.replace("复评时间：7-14天内", "复评时间：建议7-14天内")
    return normalized


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


def _remap_refs(answer: str, from_citations: List[Dict[str, Any]], target_ref_by_id: Dict[str, int]) -> str:
    if not answer:
        return ""

    def replace(match: re.Match[str]) -> str:
        num = int(match.group(1))
        idx = num - 1
        if idx < 0 or idx >= len(from_citations):
            return ""
        item_id = str(from_citations[idx].get("id") or "").strip()
        if not item_id:
            return ""
        target_num = target_ref_by_id.get(item_id)
        if not target_num:
            return ""
        return f"[{target_num}]"

    return _REF_PATTERN.sub(replace, answer)


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


def _generate_llm_field_text(section: str, context: str) -> Dict[str, Any]:
    started_at = time.time()
    retried = False
    field_prompts = {
        "diagnosis": (
            "请返回严格JSON，包含字段：diagnosis, evidence_item_ids。"
            "输出 3-5 句中文，不少于 60 字，需包含风险等级与温度范围信息，"
            "仅输出谨慎、客观的诊断结论，并使用引用编号（如[1]）。"
        ),
        "doctor_opinion": (
            "请返回严格JSON，包含字段：doctor_opinion, evidence_item_ids。"
            "输出 3-5 句中文，不少于 60 字，需包含可执行建议与复评提示，"
            "并明确写出‘仅供参考’，使用引用编号（如[1]）。"
            "禁止输出任何绝对日期（如2023-10-15）；复评仅可使用相对时间（如‘7-14天内复评’）。"
        ),
        "report_note": (
            "请返回严格JSON，包含字段：report_note, evidence_item_ids。"
            "输出 2-4 句中文，不少于 45 字，强调报告适用边界、检查前提或谨慎解释要求，"
            "并明确写出‘仅供参考’，使用引用编号（如[1]）。"
            "禁止输出任何绝对日期，复评只允许相对时间表达。"
        ),
        "health_advice": (
            "请返回严格JSON，包含字段：health_advice, evidence_item_ids。"
            "输出 4-8 条可执行的中文保健建议，总字数不少于 80 字，"
            "可覆盖作息、保暖、饮食、活动、复评观察点等，并明确写出‘仅供参考’，"
            "使用引用编号（如[1]）。"
            "禁止输出任何绝对日期，复评只允许相对时间表达（如7-14天内）。"
        ),
    }
    output_field = section
    base_prompt = _SYSTEM_PROMPT + "\n\n" + context + field_prompts[section]
    text = _ollama_generate(base_prompt, temperature=0.2, max_tokens=700)
    data = _extract_json_block(text) or {}
    value = _normalize_generated_text(data.get(output_field))
    result = {
        output_field: value,
        "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids")),
    }

    min_len = 60 if section in ("diagnosis", "doctor_opinion", "health_advice") else 45
    if len(value) < min_len:
        retried = True
        retry_prompt = (
            _SYSTEM_PROMPT
            + "\n\n"
            + context
            + field_prompts[section]
            + f"请进一步展开，{output_field} 不少于 {max(min_len, 90 if section != 'report_note' else 70)} 字。"
        )
        text = _ollama_generate(retry_prompt, temperature=0.2, max_tokens=900)
        data = _extract_json_block(text) or {}
        result = {
            output_field: _normalize_generated_text(data.get(output_field) or value),
            "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids") or result["evidence_item_ids"]),
        }
    result["_metrics"] = {
        "section": section,
        "retried": retried,
        "input_chars": len(context),
        "output_chars": len(str(result.get(output_field) or "")),
        "elapsed_sec": round(time.time() - started_at, 3),
    }
    return result


def _generate_llm_plan_text(context: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    started_at = time.time()
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
    result = {
        "treatment_plan_text": str(data.get("treatment_plan_text") or text or "").strip(),
        "evidence_item_ids": _parse_evidence_ids(data.get("evidence_item_ids")),
    }
    result["_metrics"] = {
        "section": "treatment_plan_text",
        "retried": False,
        "input_chars": len(context),
        "output_chars": len(str(result.get("treatment_plan_text") or "")),
        "elapsed_sec": round(time.time() - started_at, 3),
    }
    return result


def generate_report_ai(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, Any]:
    _log_rag_runtime_config_once()
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

    retrieval_started_at = time.time()
    section_retrieval_result = retrieve_context_by_section(report, emr)
    retrieval_elapsed = time.time() - retrieval_started_at
    retrieval_result = section_retrieval_result.get("merged") or {}
    retrieved_context = str(retrieval_result.get("context") or "")
    citations = retrieval_result.get("citations") or []
    if not retrieval_result.get("items"):
        logging.info("[RAG] completed record_id=%s with 0 hits", record_id)
        return {
            "model": OLLAMA_MODEL,
            "retrieved_context": "",
            "retrieved_items": [],
            "section_queries": section_retrieval_result.get("section_queries") or {},
            "section_retrieval": section_retrieval_result.get("sections") or {},
            "report_note": "知识库未找到依据，无法确认。",
            "evidence_item_ids": [],
        }

    logging.info(
        "[RAG] completed record_id=%s hits=%d refs=%s retrieval_elapsed=%.2fs",
        record_id,
        len(retrieval_result.get("items") or []),
        [str(item.get("id") or "") for item in citations],
        retrieval_elapsed,
    )

    if not _ollama_available():
        logging.warning("[RAG-LLM] skipped record_id=%s: ollama_unavailable", record_id)
        return {
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
            "section_queries": section_retrieval_result.get("section_queries") or {},
            "section_retrieval": section_retrieval_result.get("sections") or {},
            "report_note": "LLM服务暂不可用，已跳过AI生成，请稍后重试。",
            "evidence_item_ids": [],
        }

    merged_ref_by_id = {
        str(citation.get("id") or "").strip(): index
        for index, citation in enumerate(citations, start=1)
        if str(citation.get("id") or "").strip()
    }
    section_queries = section_retrieval_result.get("section_queries") or {}
    section_retrieval = section_retrieval_result.get("sections") or {}

    diag_payload: Dict[str, Any] = {}
    opinion_payload: Dict[str, Any] = {}
    note_payload: Dict[str, Any] = {}
    health_payload: Dict[str, Any] = {}
    plan_text = ""
    plan_evidence_ids: List[str] = []
    health_advice_text = ""
    health_evidence_ids: List[str] = []
    plan_payload: Dict[str, Any] = {}

    diagnosis_section = section_retrieval.get("diagnosis") or {}
    diagnosis_context = _build_llm_context_for_section(
        report, emr, "diagnosis", retrieved_context=str(diagnosis_section.get("context") or "")
    )
    opinion_section = section_retrieval.get("doctor_opinion") or {}
    opinion_context = _build_llm_context_for_section(
        report, emr, "doctor_opinion", retrieved_context=str(opinion_section.get("context") or "")
    )
    note_section = section_retrieval.get("report_note") or {}
    note_context = _build_llm_context_for_section(
        report, emr, "report_note", retrieved_context=str(note_section.get("context") or "")
    )
    health_section = section_retrieval.get("health_advice") or {}
    health_context = _build_llm_context_for_section(
        report, emr, "health_advice", retrieved_context=str(health_section.get("context") or "")
    )
    plan = report.get("treatment_plan") or {}
    plan_section = section_retrieval.get("treatment_plan_text") or {}
    plan_context = _build_llm_context_for_section(
        report, emr, "treatment_plan_text", retrieved_context=str(plan_section.get("context") or "")
    )

    def _run_diagnosis() -> Dict[str, Any]:
        return _generate_llm_field_text("diagnosis", diagnosis_context)

    def _run_opinion() -> Dict[str, Any]:
        return _generate_llm_field_text("doctor_opinion", opinion_context)

    def _run_note() -> Dict[str, Any]:
        return _generate_llm_field_text("report_note", note_context)

    def _run_health() -> Dict[str, Any]:
        return _generate_llm_field_text("health_advice", health_context)

    def _run_plan() -> Dict[str, Any]:
        if isinstance(plan, dict):
            return _generate_llm_plan_text(plan_context, plan)
        return {}

    _tasks = {
        "diagnosis": _run_diagnosis,
        "doctor_opinion": _run_opinion,
        "report_note": _run_note,
        "health_advice": _run_health,
        "treatment_plan_text": _run_plan,
    }
    llm_started_at = time.time()
    _results: Dict[str, Any] = {}
    section_workers = max(1, min(len(_tasks), OLLAMA_SECTION_WORKERS))
    with ThreadPoolExecutor(max_workers=section_workers) as _executor:
        _futures = {_executor.submit(fn): name for name, fn in _tasks.items()}
        for _future in as_completed(_futures):
            _results[_futures[_future]] = _future.result()
    llm_elapsed = time.time() - llm_started_at

    diag_payload = _results.get("diagnosis") or {}
    opinion_payload = _results.get("doctor_opinion") or {}
    note_payload = _results.get("report_note") or {}
    health_payload = _results.get("health_advice") or {}
    plan_payload = _results.get("treatment_plan_text") or {}

    for section_name, section_payload in (
        ("diagnosis", diag_payload),
        ("doctor_opinion", opinion_payload),
        ("report_note", note_payload),
        ("health_advice", health_payload),
        ("treatment_plan_text", plan_payload),
    ):
        metrics = section_payload.get("_metrics") if isinstance(section_payload, dict) else None
        if isinstance(metrics, dict):
            logging.info(
                "[RAG-LLM] record_id=%s section=%s retried=%s input_chars=%s output_chars=%s elapsed=%.2fs",
                record_id,
                section_name,
                metrics.get("retried"),
                metrics.get("input_chars"),
                metrics.get("output_chars"),
                float(metrics.get("elapsed_sec") or 0.0),
            )
    logging.info("[RAG-LLM] record_id=%s overall_elapsed=%.2fs", record_id, llm_elapsed)
    if isinstance(plan, dict):
        plan_text = str(plan_payload.get("treatment_plan_text") or "").strip()
        plan_evidence_ids = _parse_evidence_ids(plan_payload.get("evidence_item_ids"))
    health_advice_text = str(health_payload.get("health_advice") or "").strip()
    health_evidence_ids = _parse_evidence_ids(health_payload.get("evidence_item_ids"))

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
        "section_queries": section_retrieval_result.get("section_queries") or {},
        "section_retrieval": section_retrieval_result.get("sections") or {},
    }

    diagnosis_citations = diagnosis_section.get("citations") or []
    doctor_opinion_citations = opinion_section.get("citations") or []
    report_note_citations = note_section.get("citations") or []
    health_advice_citations = health_section.get("citations") or []
    plan_citations = (section_retrieval.get("treatment_plan_text") or {}).get("citations") or []

    if diag_payload.get("diagnosis"):
        diagnosis_text = _strip_invalid_refs(str(diag_payload["diagnosis"]), len(diagnosis_citations))
        payload["diagnosis"] = _remap_refs(diagnosis_text, diagnosis_citations, merged_ref_by_id)
    if opinion_payload.get("doctor_opinion"):
        doctor_opinion_text = _normalize_followup_date_text(
            _strip_invalid_refs(str(opinion_payload["doctor_opinion"]), len(doctor_opinion_citations))
        )
        payload["doctor_opinion"] = _remap_refs(doctor_opinion_text, doctor_opinion_citations, merged_ref_by_id)
    if note_payload.get("report_note"):
        report_note_text = _normalize_followup_date_text(
            _strip_invalid_refs(str(note_payload["report_note"]), len(report_note_citations))
        )
        payload["report_note"] = _remap_refs(report_note_text, report_note_citations, merged_ref_by_id)
    if health_advice_text:
        normalized_health_advice = _normalize_followup_date_text(
            _strip_invalid_refs(health_advice_text, len(health_advice_citations))
        )
        payload["health_advice"] = _remap_refs(normalized_health_advice, health_advice_citations, merged_ref_by_id)
    if plan_text:
        treatment_plan_text = _normalize_followup_date_text(
            _strip_invalid_refs(plan_text, len(plan_citations))
        )
        payload["treatment_plan_text"] = _remap_refs(treatment_plan_text, plan_citations, merged_ref_by_id)

    diagnosis_evidence_ids = _parse_evidence_ids(diag_payload.get("evidence_item_ids"))
    diagnosis_evidence_ids.extend(_parse_evidence_ids(opinion_payload.get("evidence_item_ids")))
    diagnosis_evidence_ids.extend(_parse_evidence_ids(note_payload.get("evidence_item_ids")))
    diagnosis_evidence_ids.extend(_parse_evidence_ids(health_payload.get("evidence_item_ids")))
    diagnosis_evidence_ids.extend(
        _resolve_ref_ids(
            "\n".join(
                [
                    str(payload.get("diagnosis") or ""),
                    str(payload.get("doctor_opinion") or ""),
                    str(payload.get("report_note") or ""),
                    str(payload.get("health_advice") or ""),
                    json.dumps(diag_payload.get("evidence_item_ids") or [], ensure_ascii=False),
                    json.dumps(opinion_payload.get("evidence_item_ids") or [], ensure_ascii=False),
                    json.dumps(note_payload.get("evidence_item_ids") or [], ensure_ascii=False),
                    json.dumps(health_payload.get("evidence_item_ids") or [], ensure_ascii=False),
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
    health_evidence_ids.extend(
        _resolve_ref_ids(
            "\n".join(
                [
                    str(payload.get("health_advice") or ""),
                    json.dumps(health_payload.get("evidence_item_ids") or [], ensure_ascii=False),
                ]
            ),
            citations,
        )
    )
    if plan_evidence_ids:
        payload["plan_evidence_item_ids"] = sorted(set(plan_evidence_ids))
    if health_evidence_ids:
        payload["health_advice_evidence_item_ids"] = sorted(set(health_evidence_ids))

    merged_evidence_ids = sorted(set(diagnosis_evidence_ids + plan_evidence_ids + health_evidence_ids))
    payload["evidence_item_ids"] = merged_evidence_ids
    payload["citations"] = citations

    return payload
