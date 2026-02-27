from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") != "0"


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


def _build_llm_context(report: Dict[str, Any], emr: Dict[str, Any]) -> str:
    patient = report.get("patient") or emr.get("patient") or {}
    analysis = report.get("analysis") or {}
    metrics = (analysis.get("temperature_metrics") or {}) if isinstance(analysis, dict) else {}
    risk_level = str(analysis.get("risk_level") or "-")
    summary = str(analysis.get("summary") or "-")
    abnormal_regions = []
    if isinstance(analysis, dict):
        abnormal_regions = (analysis.get("regional_comparison") or {}).get("abnormal_regions") or []
    body_part = patient.get("body_part") or "unknown"

    return (
        "你是一名医疗热成像评估助手。请基于以下信息生成简洁、谨慎的中文内容。"
        "输出只需客观结论，避免夸大或绝对化表述。\n"
        f"患者信息：姓名={patient.get('name','-')} 性别={patient.get('gender','-')} 年龄={patient.get('age','-')} 部位={body_part}\n"
        f"风险等级：{risk_level}\n"
        f"温度摘要：{summary}\n"
        f"温度指标：min={metrics.get('min_c')} max={metrics.get('max_c')} avg={metrics.get('avg_c')}\n"
        f"异常区域：{abnormal_regions}\n"
    )


def _generate_llm_diagnosis_and_opinion(context: str) -> Dict[str, str]:
    base_prompt = (
        context
        + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note。"
        "每个字段输出 3-5 句中文，不少于 80 字，需包含风险等级与温度范围信息，"
        "其中 doctor_opinion 和 report_note 必须明确‘仅供参考’。"
    )
    text = _ollama_generate(base_prompt, temperature=0.2, max_tokens=900)
    data = _extract_json_block(text) or {}
    result = {
        "diagnosis": str(data.get("diagnosis") or "").strip(),
        "doctor_opinion": str(data.get("doctor_opinion") or "").strip(),
        "report_note": str(data.get("report_note") or "").strip(),
    }

    def _too_short(value: str) -> bool:
        return len(value) < 80

    if any(_too_short(value) for value in result.values()):
        retry_prompt = (
            context
            + "请返回严格JSON，包含字段：diagnosis, doctor_opinion, report_note。"
            "请输出更详细的内容，每个字段不少于 120 字，分为 3-5 句，"
            "需包含风险等级、温度范围与建议要点，"
            "其中 doctor_opinion 和 report_note 必须包含‘仅供参考’。"
        )
        text = _ollama_generate(retry_prompt, temperature=0.2, max_tokens=1200)
        data = _extract_json_block(text) or {}
        result = {
            "diagnosis": str(data.get("diagnosis") or result["diagnosis"]).strip(),
            "doctor_opinion": str(data.get("doctor_opinion") or result["doctor_opinion"]).strip(),
            "report_note": str(data.get("report_note") or result["report_note"]).strip(),
        }

    return result


def _generate_llm_plan_text(context: str, plan: Dict[str, Any]) -> str:
    plan_summary = {
        "intensity_level": plan.get("intensity_level"),
        "sessions": plan.get("sessions"),
        "frequency": plan.get("frequency"),
        "target_regions": plan.get("target_regions"),
        "acupoints": plan.get("acupoints"),
    }
    prompt = (
        context
        + "以下为规则引擎生成的治疗方案要点，请生成精简但具体的中文说明（3-6句），"
        "需涵盖频次/疗程/关键部位，并标注‘仅供参考’：\n"
        + json.dumps(plan_summary, ensure_ascii=False)
    )
    return _ollama_generate(prompt, temperature=0.3, max_tokens=500)


def generate_report_ai(report: Dict[str, Any], emr: Dict[str, Any]) -> Dict[str, Any]:
    if not OLLAMA_ENABLED:
        return {}

    context = _build_llm_context(report, emr)
    diag_payload = _generate_llm_diagnosis_and_opinion(context)
    plan_text = ""
    plan = report.get("treatment_plan") or {}
    if isinstance(plan, dict):
        plan_text = _generate_llm_plan_text(context, plan).strip()

    payload: Dict[str, Any] = {"model": OLLAMA_MODEL}
    if diag_payload.get("diagnosis"):
        payload["diagnosis"] = diag_payload["diagnosis"]
    if diag_payload.get("doctor_opinion"):
        payload["doctor_opinion"] = diag_payload["doctor_opinion"]
    if diag_payload.get("report_note"):
        payload["report_note"] = diag_payload["report_note"]
    if plan_text:
        payload["treatment_plan_text"] = plan_text

    return payload
