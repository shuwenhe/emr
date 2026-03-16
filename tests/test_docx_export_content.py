from pathlib import Path
import sys

from docx import Document


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "ingestion") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "ingestion"))

from reports.python import docx_generator as docx_module


def test_generate_docx_report_excludes_evidence_and_rag_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(docx_module, "REPORTS_DIR", tmp_path)

    report = {
        "report_id": "report-001",
        "created_at": "2026-03-10T14:53:00",
        "patient": {
            "name": "测试患者",
            "gender": "male",
            "age": 45,
            "body_part": "背部",
        },
        "analysis": {
            "temperature_metrics": {
                "min_c": 30.1,
                "max_c": 36.8,
                "avg_c": 33.3,
                "count": 128,
            },
            "risk_level": "medium",
            "regional_comparison": {
                "abnormal_regions": [
                    {
                        "region": "r2_c2",
                        "region_cn": "中背脊柱旁区",
                        "status": "high",
                        "avg_c": 35.2,
                        "delta_c": 1.1,
                    }
                ]
            },
        },
        "diagnosis": "测试诊断内容。",
        "doctor_opinion": "测试医生意见。",
        "report_note": "测试报告说明。",
        "treatment_plan_text": "测试治疗建议。",
        "citations": [
            {"id": "KB-001", "title": "热成像判读规范", "source": "热成像判读规范（试行）"}
        ],
        "retrieved_items": [
            {"id": "KB-002", "title": "慢性疼痛管理", "source": "院内门诊随访建议单", "tags": ["疼痛"]}
        ],
        "evidence_item_ids": ["KB-001", "KB-002"],
        "diagnosis_evidence_item_ids": ["KB-001"],
        "plan_evidence_item_ids": ["KB-002"],
    }
    emr = {
        "emr_id": "EMR-001",
        "patient": report["patient"],
        "created_at": report["created_at"],
    }

    output_path = docx_module.generate_docx_report(report, emr)

    assert output_path.exists()

    doc = Document(str(output_path))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)

    assert "证据依据" not in text
    assert "RAG 命中条目" not in text
    assert "热成像判读规范" not in text
    assert "慢性疼痛管理" not in text
    assert "诊断结论" in text
    assert "医生意见" in text
    assert "治疗建议" in text
