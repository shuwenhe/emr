#!/usr/bin/env python3
"""Import one raw case text and split into 3 KB rows.

Rows created:
- report_template
- treatment_guideline
- follow_up_rule
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from validate_kb_jsonl import validate_rows


SECTION_RE = re.compile(r"^\s*([一二三四五六七八九十]+)[、.．]\s*(.+?)\s*$", re.MULTILINE)


def parse_sections(text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return {"全文": text.strip()}

    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections[title] = body
    return sections


def pick_section(sections: dict[str, str], keywords: list[str]) -> str:
    for key, value in sections.items():
        if any(k in key for k in keywords):
            return value
    return ""


def detect_gender(text: str) -> str | None:
    if "男" in text and "女" not in text:
        return "male"
    if "女" in text and "男" not in text:
        return "female"
    return None


def detect_age(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*岁", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def detect_body_parts(text: str) -> list[str]:
    mapping = {
        "肋": "肋部",
        "足": "足部",
        "拇趾": "第一跖趾关节",
        "膝": "膝关节",
        "腰": "腰背",
        "颈": "颈肩",
        "肩": "颈肩",
        "四肢": "四肢",
    }
    parts: list[str] = []
    for k, v in mapping.items():
        if k in text and v not in parts:
            parts.append(v)
    if not parts:
        parts.append("未特指部位")
    return parts


def detect_risk_levels(text: str) -> list[str]:
    vas = None
    m = re.search(r"VAS[^\d]*(\d+)", text, re.IGNORECASE)
    if m:
        try:
            vas = int(m.group(1))
        except ValueError:
            vas = None

    if any(k in text for k in ["剧烈", "明显受限", "高风险", "加重"]) or (vas is not None and vas >= 7):
        return ["high"]
    if any(k in text for k in ["反复", "中度", "受限"]) or (vas is not None and 4 <= vas < 7):
        return ["medium"]
    return ["low"]


def first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def extract_case_title(raw_text: str, sections: dict[str, str]) -> str:
    overview = pick_section(sections, ["病历概述", "概述"]) or raw_text
    line = first_non_empty_line(overview)
    if line:
        return line[:80]
    return "未命名病例"


def extract_diagnosis(raw_text: str, sections: dict[str, str]) -> str:
    diagnosis = pick_section(sections, ["诊断"]) or ""
    if diagnosis:
        return diagnosis[:320]
    return first_non_empty_line(raw_text)[:320]


def find_next_id(existing_ids: set[str], prefix: str) -> str:
    n = 1
    while True:
        candidate = f"{prefix}{n:04d}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def build_rows(raw_text: str, sections: dict[str, str], existing_ids: set[str], source_name: str) -> list[dict[str, Any]]:
    overview = pick_section(sections, ["病历概述", "现病史", "主诉"]) or raw_text
    treatment = pick_section(sections, ["治疗过程", "治疗"]) or ""
    follow_up = pick_section(sections, ["随访", "复诊"]) or ""
    diagnosis = extract_diagnosis(raw_text, sections)

    age = detect_age(overview)
    gender = detect_gender(overview)
    patient_scope = ["adult"]
    if age is not None and age >= 60 and "elderly" not in patient_scope:
        patient_scope.append("elderly")
    if gender in {"male", "female"}:
        patient_scope.append(gender)

    body_parts = detect_body_parts(raw_text)
    risk_levels = detect_risk_levels(raw_text)

    title = extract_case_title(raw_text, sections)
    diagnosis_short = diagnosis.replace("\n", " ").strip()

    rpt_id = find_next_id(existing_ids, "KB-IR-RPT-C")
    existing_ids.add(rpt_id)
    tx_id = find_next_id(existing_ids, "KB-IR-TX-C")
    existing_ids.add(tx_id)
    fup_id = find_next_id(existing_ids, "KB-IR-FUP-C")
    existing_ids.add(fup_id)

    report_content = (
        f"病例要点：{diagnosis_short}。"
        f"报告建议结合病史与体征，重点描述疼痛特征、受累部位及诱发因素。"
        f"对高风险信号应提示及时专科评估，避免绝对化诊断表达。"
    )

    treatment_content = (
        f"病例治疗建议：{(treatment[:220] if treatment else '以规范药物治疗与局部保护为基础，联合生活方式管理。')}"
        f"报告可强调减轻负荷、改善睡眠与情绪支持，并根据症状变化动态调整方案。"
    )

    follow_up_content = (
        f"病例随访建议：{(follow_up[:220] if follow_up else '建议设置短期症状复评和中期功能随访双节点。')}"
        f"随访时建议记录疼痛评分、活动受限范围与生活质量变化。"
    )

    common = {
        "source": source_name,
        "source_type": "weak_observation",
        "priority": 8,
        "status": "active",
        "patient_scope": patient_scope,
        "body_parts": body_parts,
        "risk_levels": risk_levels,
        "evidence_level": "weak_observation",
    }

    return [
        {
            "id": rpt_id,
            "title": f"病例模板：{title[:40]}",
            "content": report_content,
            "category": "report_template",
            "report_sections": ["diagnosis", "doctor_opinion", "report_note"],
            "tags": ["病例模板", "真实病例", "个体化"],
            "applicable_conditions": ["存在相似主诉与体征", "需要病例化措辞"],
            "contraindications": ["关键诊断信息缺失时需补充检查"],
            "retrieval_hints": [diagnosis_short[:60], "病例经验", "个体化表达"],
            "structured_advice": {
                "template_key": "case_based_template",
                "diagnosis_anchor": diagnosis_short[:120],
            },
            **common,
        },
        {
            "id": tx_id,
            "title": f"病例治疗建议：{title[:36]}",
            "content": treatment_content,
            "category": "treatment_guideline",
            "report_sections": ["treatment_plan_text", "doctor_opinion", "health_advice"],
            "tags": ["病例治疗", "个体化", "方案优化"],
            "applicable_conditions": ["临床诊断已明确", "需输出可执行治疗建议"],
            "contraindications": ["症状快速恶化时应先专科评估"],
            "retrieval_hints": ["治疗过程", "局部干预", "生活方式管理"],
            "structured_advice": {
                "template_key": "case_based_treatment",
                "supports": ["symptom_relief", "function_recovery"],
            },
            **common,
        },
        {
            "id": fup_id,
            "title": f"病例随访规则：{title[:36]}",
            "content": follow_up_content,
            "category": "follow_up_rule",
            "report_sections": ["doctor_opinion", "health_advice", "report_note"],
            "tags": ["病例随访", "复评", "疗效跟踪"],
            "applicable_conditions": ["需输出复评计划", "存在可量化症状指标"],
            "contraindications": ["出现红旗症状时不应等待常规随访"],
            "retrieval_hints": ["随访情况", "复评节点", "疗效趋势"],
            "structured_advice": {
                "template_key": "case_based_followup",
                "tracking_items": ["VAS", "functional_status", "quality_of_life"],
            },
            **common,
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import one case text into KB JSONL as 3 rows")
    parser.add_argument("--case-file", required=True, help="Path to raw case text file")
    parser.add_argument(
        "--kb-jsonl",
        default="./rag/kb/knowledge_base.jsonl",
        help="KB jsonl path (default: ./rag/kb/knowledge_base.jsonl)",
    )
    parser.add_argument(
        "--kb-json",
        default="./rag/kb/knowledge_base.json",
        help="KB json path to sync after import (default: ./rag/kb/knowledge_base.json)",
    )
    parser.add_argument(
        "--source-name",
        default="病例原文导入",
        help="Source label written into KB rows",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print generated rows without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    case_path = Path(args.case_file).resolve()
    kb_jsonl_path = Path(args.kb_jsonl).resolve()
    kb_json_path = Path(args.kb_json).resolve()

    if not case_path.exists() or not case_path.is_file():
        print(f"[ERROR] case file not found: {case_path}")
        return 2
    if not kb_jsonl_path.exists() or not kb_jsonl_path.is_file():
        print(f"[ERROR] kb jsonl file not found: {kb_jsonl_path}")
        return 2

    raw_text = case_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        print(f"[ERROR] empty case file: {case_path}")
        return 2

    sections = parse_sections(raw_text)

    existing_rows: list[dict[str, Any]] = []
    with kb_jsonl_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] invalid kb jsonl at line {line_no}: {exc}")
                return 1
            if not isinstance(obj, dict):
                print(f"[ERROR] invalid kb jsonl row type at line {line_no}")
                return 1
            existing_rows.append(obj)

    existing_ids = {str(row.get("id") or "").strip() for row in existing_rows if str(row.get("id") or "").strip()}
    new_rows = build_rows(raw_text, sections, existing_ids, args.source_name)

    merged = existing_rows + new_rows
    errors = validate_rows(merged)
    if errors:
        print("[WARN] validation failed after merge")
        for err in errors[:50]:
            print(f"  - {err}")
        # By default do not abort on validation errors to allow incremental fixes.
        # To enforce strict validation set environment var EMR_STRICT_KB_VALIDATION=1
        import os
        if os.environ.get("EMR_STRICT_KB_VALIDATION") == "1":
            print("[ERROR] strict validation enabled, aborting")
            return 1

    if args.dry_run:
        print("[DRY-RUN] generated rows:")
        for row in new_rows:
            print(json.dumps(row, ensure_ascii=False))
        return 0

    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in merged)
    if content:
        content += "\n"

    tmp = kb_jsonl_path.with_suffix(kb_jsonl_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(kb_jsonl_path)

    # Sync JSON mirror.
    payload = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
    tmp_json = kb_json_path.with_suffix(kb_json_path.suffix + ".tmp")
    kb_json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_json.write_text(payload, encoding="utf-8")
    tmp_json.replace(kb_json_path)

    print(f"[OK] imported case into KB: +{len(new_rows)} rows total={len(merged)}")
    print("[OK] new ids:", ", ".join(r["id"] for r in new_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
