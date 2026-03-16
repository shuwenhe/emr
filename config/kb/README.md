# Infrared Report RAG KB Spec

## Goal

This knowledge base is for infrared thermal imaging report generation, not for general QA.
Each knowledge item should support at least one report field:

- `diagnosis`
- `doctor_opinion`
- `treatment_plan_text`
- `report_note`
- `contraindications`
- `follow_up`

## Directory Layout

Recommended layout under `config/kb/`:

```text
config/kb/
  README.md
  infrared_report_kb.sample.jsonl
  01_sop/
    check_preparation.jsonl
    acquisition_environment.jsonl
    calibration_and_pose.jsonl
  02_interpretation/
    symmetry_rules.jsonl
    hotspot_rules.jsonl
    coldspot_rules.jsonl
    risk_stratification.jsonl
  03_report_writing/
    diagnosis_templates.jsonl
    doctor_opinion_templates.jsonl
    report_note_templates.jsonl
  04_treatment/
    moxibustion_guidance.jsonl
    rehab_guidance.jsonl
    follow_up_rules.jsonl
  05_safety/
    contraindications.jsonl
    referral_rules.jsonl
  90_eval/
    retrieval_goldset.jsonl
```

Rules:

- One line per JSON object.
- UTF-8, no comments, no trailing commas.
- Keep each item atomic: one rule, one caution, one interpretation principle, or one treatment recommendation.
- Prefer short evidence units over long paragraphs.

## JSONL Schema

Required fields:

```json
{
  "id": "KB-IR-INT-0001",
  "title": "左右对称差异优先于绝对温度",
  "content": "体表温度判读应优先比较左右对称区域差异，而不是仅依据单次绝对温度值下结论。",
  "category": "interpretation_rule",
  "report_sections": ["diagnosis", "doctor_opinion"],
  "tags": ["对称性", "温差", "判读原则"],
  "source": "热成像判读规范（试行）",
  "source_type": "guideline",
  "priority": 8,
  "status": "active"
}
```

Recommended optional fields:

```json
{
  "applicable_conditions": ["左右对称ROI可比较", "采集流程合规"],
  "contraindications": ["环境温度波动过大时慎用单次结论"],
  "patient_scope": ["adult"],
  "body_parts": ["颈肩", "腰背"],
  "risk_levels": ["low", "medium"],
  "evidence_level": "consensus",
  "retrieval_hints": ["左右温差", "对称性", "异常热点"],
  "structured_advice": {
    "follow_up_days_min": 7,
    "follow_up_days_max": 14,
    "action": "复测热成像并结合临床表现复评"
  }
}
```

## Field Definitions

- `id`: Stable unique ID. Suggested pattern: `KB-IR-<domain>-<number>`.
- `title`: Short retrieval-friendly title.
- `content`: Final knowledge text used for retrieval and citation.
- `category`: One of the controlled categories below.
- `report_sections`: Which report fields may consume this item.
- `tags`: Search and rerank hints.
- `source`: Human-readable source name.
- `source_type`: Provenance type.
- `priority`: Integer `1-10`. Higher means easier to surface.
- `status`: `active`, `draft`, `deprecated`.
- `applicable_conditions`: Preconditions for using the item.
- `contraindications`: When not to apply this item.
- `patient_scope`: Such as `adult`, `child`, `female`, `elderly`.
- `body_parts`: Relevant anatomical areas.
- `risk_levels`: `low`, `medium`, `high`.
- `evidence_level`: `expert_opinion`, `consensus`, `guideline`, `internal_sop`, `weak_observation`.
- `retrieval_hints`: Extra query terms not suitable for final report text.
- `structured_advice`: Machine-friendly fields for downstream assembly.

## Controlled Categories

Use only these category values:

- `sop_preparation`
- `sop_acquisition`
- `sop_calibration`
- `interpretation_rule`
- `interpretation_hotspot`
- `interpretation_coldspot`
- `interpretation_symmetry`
- `risk_stratification`
- `report_template`
- `doctor_opinion_rule`
- `treatment_guideline`
- `follow_up_rule`
- `contraindication`
- `referral_rule`

## Report Section Mapping

Suggested mapping:

- `diagnosis`: `interpretation_rule`, `interpretation_hotspot`, `interpretation_coldspot`, `risk_stratification`
- `doctor_opinion`: `doctor_opinion_rule`, `interpretation_rule`, `contraindication`
- `treatment_plan_text`: `treatment_guideline`, `follow_up_rule`, `contraindication`
- `report_note`: `report_template`, `sop_preparation`, `sop_acquisition`

## Authoring Rules

- Avoid absolute diagnoses from thermal data alone.
- Prefer conditional language: "提示", "建议结合临床", "建议复评".
- Keep one item focused on one decision point.
- Put reusable medical wording in `content`; put trigger words in `retrieval_hints`.
- If one item contains both interpretation and treatment, split it into two records.

Bad example:

```json
{"id":"bad-1","title":"热成像综合说明","content":"这里同时包含采集要求、判读原则、治疗建议和转诊条件。"}
```

Good practice:

- One item for preparation.
- One item for symmetry interpretation.
- One item for referral safety boundary.
- One item for follow-up interval.

## Naming Convention

Suggested IDs:

- `KB-IR-SOP-0001`
- `KB-IR-INT-0001`
- `KB-IR-RISK-0001`
- `KB-IR-TX-0001`
- `KB-IR-SAFE-0001`

## Evaluation Set

Keep a small retrieval evaluation file in `config/kb/90_eval/retrieval_goldset.jsonl`.

Recommended fields:

```json
{
  "case_id": "CASE-001",
  "query_features": {
    "risk_level": "medium",
    "body_part": "腰背",
    "pattern": "left_right_asymmetry",
    "delta_temp_c": 0.8
  },
  "expected_kb_ids": ["KB-IR-INT-0001", "KB-IR-RISK-0002", "KB-IR-TX-0003"]
}
```

## Migration Suggestion

Current file `rag/kb/knowledge_base.jsonl` can be migrated in two steps:

1. Add missing fields to existing 10 seed entries.
2. Split the new corpus into the category files above and concatenate them during build if needed.
