#!/usr/bin/env python3
"""Validate structured KB entries in knowledge_base.jsonl.

This script enforces a stable schema so newly added entries do not break
runtime retrieval/build pipelines.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_STRING_FIELDS = (
    "id",
    "title",
    "content",
    "category",
    "source",
    "source_type",
    "status",
)

REQUIRED_LIST_FIELDS = (
    "report_sections",
    "tags",
)

OPTIONAL_LIST_FIELDS = (
    "applicable_conditions",
    "contraindications",
    "patient_scope",
    "body_parts",
    "risk_levels",
    "retrieval_hints",
)

ALLOWED_CATEGORIES = {
    "sop_preparation",
    "sop_acquisition",
    "sop_calibration",
    "interpretation_rule",
    "interpretation_hotspot",
    "interpretation_coldspot",
    "interpretation_symmetry",
    "risk_stratification",
    "report_template",
    "doctor_opinion_rule",
    "treatment_guideline",
    "follow_up_rule",
    "contraindication",
    "referral_rule",
}

ALLOWED_REPORT_SECTIONS = {
    "diagnosis",
    "doctor_opinion",
    "treatment_plan_text",
    "report_note",
    "contraindications",
    "follow_up",
    "health_advice",
}

ALLOWED_STATUS = {"active", "draft", "deprecated"}

ALLOWED_SOURCE_TYPE = {
    "guideline",
    "internal_sop",
    "consensus",
    "expert_opinion",
    "weak_observation",
}

ALLOWED_RISK_LEVELS = {"low", "medium", "high"}

ALLOWED_EVIDENCE_LEVEL = {
    "expert_opinion",
    "consensus",
    "guideline",
    "internal_sop",
    "weak_observation",
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_string_list(value: Any, field_name: str, errors: list[str], prefix: str) -> None:
    if not isinstance(value, list):
        errors.append(f"{prefix}{field_name} must be a list")
        return
    for idx, item in enumerate(value):
        if not _is_non_empty_string(item):
            errors.append(f"{prefix}{field_name}[{idx}] must be a non-empty string")


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()

    for line_no, row in enumerate(rows, start=1):
        prefix = f"line {line_no}: "
        if not isinstance(row, dict):
            errors.append(f"{prefix}row must be a JSON object")
            continue

        for field_name in REQUIRED_STRING_FIELDS:
            if not _is_non_empty_string(row.get(field_name)):
                errors.append(f"{prefix}{field_name} must be a non-empty string")

        for field_name in REQUIRED_LIST_FIELDS:
            value = row.get(field_name)
            _validate_string_list(value, field_name, errors, prefix)
            if isinstance(value, list) and not value:
                errors.append(f"{prefix}{field_name} must not be empty")

        row_id = row.get("id")
        if _is_non_empty_string(row_id):
            if row_id in seen_ids:
                errors.append(f"{prefix}id is duplicated: {row_id}")
            else:
                seen_ids.add(row_id)

        priority = row.get("priority")
        if not isinstance(priority, int) or not (1 <= priority <= 10):
            errors.append(f"{prefix}priority must be an integer in [1, 10]")

        category = row.get("category")
        if isinstance(category, str) and category not in ALLOWED_CATEGORIES:
            errors.append(
                f"{prefix}category must be one of {sorted(ALLOWED_CATEGORIES)}; got {category!r}"
            )

        status = row.get("status")
        if isinstance(status, str) and status not in ALLOWED_STATUS:
            errors.append(f"{prefix}status must be one of {sorted(ALLOWED_STATUS)}; got {status!r}")

        source_type = row.get("source_type")
        if isinstance(source_type, str) and source_type not in ALLOWED_SOURCE_TYPE:
            errors.append(
                f"{prefix}source_type must be one of {sorted(ALLOWED_SOURCE_TYPE)}; got {source_type!r}"
            )

        report_sections = row.get("report_sections")
        if isinstance(report_sections, list):
            for section in report_sections:
                if isinstance(section, str) and section not in ALLOWED_REPORT_SECTIONS:
                    errors.append(
                        f"{prefix}report_sections includes unsupported value {section!r}; "
                        f"allowed={sorted(ALLOWED_REPORT_SECTIONS)}"
                    )

        for list_field in OPTIONAL_LIST_FIELDS:
            if list_field in row:
                _validate_string_list(row.get(list_field), list_field, errors, prefix)

        risk_levels = row.get("risk_levels")
        if isinstance(risk_levels, list):
            for level in risk_levels:
                if isinstance(level, str) and level not in ALLOWED_RISK_LEVELS:
                    errors.append(
                        f"{prefix}risk_levels includes unsupported value {level!r}; "
                        f"allowed={sorted(ALLOWED_RISK_LEVELS)}"
                    )

        evidence_level = row.get("evidence_level")
        if evidence_level is not None:
            if not isinstance(evidence_level, str):
                errors.append(f"{prefix}evidence_level must be a string if provided")
            elif evidence_level not in ALLOWED_EVIDENCE_LEVEL:
                errors.append(
                    f"{prefix}evidence_level must be one of {sorted(ALLOWED_EVIDENCE_LEVEL)}; "
                    f"got {evidence_level!r}"
                )

        structured_advice = row.get("structured_advice")
        if structured_advice is not None and not isinstance(structured_advice, dict):
            errors.append(f"{prefix}structured_advice must be an object if provided")

    return errors


def load_jsonl_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    parse_errors: list[str] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                parse_errors.append(f"line {line_no}: invalid JSON: {exc}")
                continue
            if not isinstance(obj, dict):
                parse_errors.append(f"line {line_no}: row must be a JSON object")
                continue
            rows.append(obj)

    return rows, parse_errors


def validate_jsonl_file(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows, parse_errors = load_jsonl_rows(path)
    if parse_errors:
        return rows, parse_errors
    return rows, validate_rows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate KB JSONL schema and constraints")
    parser.add_argument(
        "--kb",
        default="./rag/kb/knowledge_base.jsonl",
        help="Path to knowledge_base.jsonl (default: ./rag/kb/knowledge_base.jsonl)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    kb_path = Path(args.kb).resolve()

    if not kb_path.exists() or not kb_path.is_file():
        print(f"[ERROR] KB file not found: {kb_path}")
        return 2

    rows, errors = validate_jsonl_file(kb_path)
    if errors:
        print(f"[ERROR] KB validation failed: {kb_path}")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"[OK] KB validation passed: {kb_path} (rows={len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
