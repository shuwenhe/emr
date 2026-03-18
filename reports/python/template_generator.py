from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sys
# Add ingestion to path for config imports
_DEVICE_INGESTION_DIR = Path(__file__).resolve().parents[2] / "ingestion"
if str(_DEVICE_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_DEVICE_INGESTION_DIR))

from app.config import DATA_DIR, DEFAULT_REPORT_TEMPLATE, REPORTS_DIR, TEMPLATE_DIR


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("_", "-", "·"))


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def _resolve_image_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = DATA_DIR / path
    return path


def _read_image_bytes(path: Optional[Path]) -> Optional[bytes]:
    if not path or not path.exists():
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def _gender_cn(value: Optional[str]) -> str:
    if not value:
        return "-"
    if value in {"male", "Male", "MALE", "m", "M", "男"}:
        return "男"
    if value in {"female", "Female", "FEMALE", "f", "F", "女"}:
        return "女"
    return str(value)


def _to_temp_text(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.1f}"
    except Exception:
        return str(value)


def _text(value: Any, default: str = "-") -> str:
    raw = str(value or "").strip()
    return raw or default


def _risk_level_cn(value: Any) -> str:
    level = str(value or "").strip().lower()
    if level == "high":
        return "高风险"
    if level == "medium":
        return "中风险"
    if level == "low":
        return "低风险"
    return "未知"


def _risk_score_from_level(value: Any) -> int:
    level = str(value or "").strip().lower()
    if level == "high":
        return 75
    if level == "medium":
        return 50
    if level == "low":
        return 25
    return 0


def _section_name(name: str) -> str:
    text = str(name or "")
    if any(key in text for key in ("额", "眼", "鼻", "口", "脸", "颊", "头")):
        return "头面部"
    if any(key in text for key in ("颈", "肩")):
        return "颈肩部"
    if any(key in text for key in ("背", "脊")):
        return "脊柱背部"
    if any(key in text for key in ("胸", "腹", "腰", "肾", "臀")):
        return "胸腹部"
    if any(key in text for key in ("臂", "腿", "手", "肘")):
        return "四肢部"
    return "综合评估"


def _severity_from_delta(delta_value: Any) -> str:
    try:
        delta = abs(float(delta_value))
    except Exception:
        return "轻"
    if delta >= 1.5:
        return "重"
    if delta >= 0.8:
        return "中"
    return "轻"


def _split_advice_lines(*values: Any) -> List[str]:
    lines: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for chunk in re.split(r"[\n；;。]+", text):
            item = chunk.strip()
            if item:
                lines.append(item)
    return lines


def _select_template(report: Dict[str, Any], template_name: Optional[str]) -> Path:
    if template_name:
        candidate = TEMPLATE_DIR / template_name
        if candidate.exists():
            return candidate
    env_template = os.getenv("REPORT_TEMPLATE")
    if env_template:
        candidate = TEMPLATE_DIR / env_template
        if candidate.exists():
            return candidate
    analysis = report.get("analysis") or {}
    metrics = analysis.get("temperature_metrics") if isinstance(analysis, dict) else None
    if metrics and TEMPLATE_DIR.joinpath(DEFAULT_REPORT_TEMPLATE).exists():
        return TEMPLATE_DIR / DEFAULT_REPORT_TEMPLATE
    fallback = TEMPLATE_DIR / "56474CC8AB1E4E79A4220605F8770FFA.tpl"
    return fallback if fallback.exists() else TEMPLATE_DIR / DEFAULT_REPORT_TEMPLATE


def _load_fastreport():
    try:
        import clr  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "FastReport 依赖的 .NET 运行时未就绪（pythonnet/mono 或 coreclr 缺失）。"
        ) from exc

    assembly_path = os.getenv("FASTREPORT_ASSEMBLY")
    if assembly_path:
        clr.AddReference(assembly_path)
    else:
        clr.AddReference("FastReport")

    clr.AddReference("System.Data")
    clr.AddReference("FastReport.Export.Pdf")

    from FastReport import Report  # type: ignore
    from FastReport.Export.Pdf import PDFSimpleExport  # type: ignore
    from System import Array, Byte, DBNull, Int32, String  # type: ignore
    from System.Data import DataSet, DataTable  # type: ignore

    return Report, PDFSimpleExport, DataSet, DataTable, Array, Byte, DBNull, Int32, String


def _build_tables(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    array_type,
    int_type,
    string_type,
) -> List[Tuple[str, Dict[str, Any], List[Dict[str, Any]]]]:
    analysis = report.get("analysis") or {}
    patient = report.get("patient") or emr.get("patient") or {}
    clinical = report.get("clinical") or {}
    metrics = analysis.get("temperature_metrics") if isinstance(analysis, dict) else {}
    created_at = report.get("created_at") or emr.get("created_at")
    created_dt = _parse_datetime(created_at)
    roi_analysis = analysis.get("roi_analysis") if isinstance(analysis, dict) else {}
    roi_list = roi_analysis.get("roi_list") if isinstance(roi_analysis, dict) else []
    if not isinstance(roi_list, list):
        roi_list = []
    regional = analysis.get("regional_comparison") if isinstance(analysis, dict) else {}
    abnormal_regions = regional.get("abnormal_regions") if isinstance(regional, dict) else []
    if not isinstance(abnormal_regions, list):
        abnormal_regions = []

    exam_rows = [
        {
            "单位名称": emr.get("hospital") or emr.get("unit") or "-",
            "createdate": created_at or "-",
            "检查项目名称": patient.get("body_part") or "-",
            "报告编码": report.get("report_id") or "-",
            "医师名称": clinical.get("doctor") or clinical.get("doctor_name") or "-",
        }
    ]

    person_rows = [
        {
            "患者名称": patient.get("name") or "-",
            "性别": _gender_cn(patient.get("gender")),
            "年龄": patient.get("age") or "-",
        }
    ]

    imgtemprs_rows = [
        {
            "Name": "整体",
            "Aver": _to_temp_text(metrics.get("avg_c")),
            "Max": _to_temp_text(metrics.get("max_c")),
            "Min": _to_temp_text(metrics.get("min_c")),
        }
    ]

    temperature_labels = report.get("thermal_marked_labels") or []
    if isinstance(temperature_labels, list):
        for item in temperature_labels:
            if not isinstance(item, dict):
                continue
            imgtemprs_rows.append(
                {
                    "Name": item.get("label") or item.get("name") or "-",
                    "Aver": _to_temp_text(item.get("avg")),
                    "Max": _to_temp_text(item.get("max")),
                    "Min": _to_temp_text(item.get("min")),
                }
            )

    marked_image = _resolve_image_path(
        report.get("thermal_marked_image") or report.get("thermal_roi_labeled_image")
    )
    marked_bytes = _read_image_bytes(marked_image)
    thermal_images = report.get("thermal_images") or []

    qsimgs_rows: List[Dict[str, Any]] = []
    line_index = 1
    if marked_bytes:
        qsimgs_rows.append(
            {
                "Line": line_index,
                "BigFileBlob1": array_type(marked_bytes),
                "FileBlob1": array_type(marked_bytes),
            }
        )
        line_index += 1

    for value in thermal_images:
        image_path = _resolve_image_path(str(value))
        image_bytes = _read_image_bytes(image_path)
        if not image_bytes:
            continue
        qsimgs_rows.append(
            {
                "Line": line_index,
                "BigFileBlob1": array_type(image_bytes),
                "FileBlob1": array_type(image_bytes),
            }
        )
        line_index += 1

    summary = (analysis.get("summary") if isinstance(analysis, dict) else "") or "-"
    doctor_opinion = report.get("doctor_opinion") or "-"

    qsgroup1_rows = [
        {"ID": 1, "级别": 2, "项目名称": "数据分析"},
        {"ID": 2, "级别": 3, "项目名称": "检查结果"},
        {"ID": 3, "级别": 4, "项目名称": "红外评估意见"},
    ]

    qsgroup2_rows = [
        {"Id": 10, "PID": 1, "项目名称": "热图显示区"},
        {"Id": 20, "PID": 2, "项目名称": "总结"},
        {"Id": 30, "PID": 3, "项目名称": "红外评估意见"},
    ]

    qsgroup3_rows = [
        {"Id": 100, "PID": 10, "项目名称": "热图分析"},
        {"Id": 200, "PID": 20, "项目名称": "结论"},
    ]

    qslist_rows = [
        {
            "ID": 1000,
            "PID": 10,
            "项目名称": "热图显示区",
            "图像提示": summary,
            "建议": doctor_opinion,
        },
        {
            "ID": 1001,
            "PID": 20,
            "项目名称": "总结",
            "图像提示": summary,
            "建议": doctor_opinion,
        },
    ]

    cover_rows = [
        {
            "编号": _text(report.get("report_id") or emr.get("emr_id")),
            "姓名": _text(patient.get("name")),
            "性别": _gender_cn(patient.get("gender")),
            "年龄": _text(patient.get("age")),
            "日期": created_dt.strftime("%Y-%m-%d"),
            "单位名称": _text(emr.get("hospital") or emr.get("unit") or "张氏疼痛外治中心"),
            "系统名称": "红外影像云平台-红外影像热层析系统",
            "报告标题": "红外热成像评估报告",
            "英文标题": "INFRARED THERMAL IMAGEING HEALTH REPORT",
        }
    ]

    section_buckets: Dict[str, Dict[str, Any]] = {}
    for roi in roi_list:
        if not isinstance(roi, dict):
            continue
        roi_name = _text(roi.get("name"), "")
        if not roi_name:
            continue
        section = _section_name(roi_name)
        bucket = section_buckets.setdefault(
            section,
            {"names": [], "temps": [], "counts": [], "risk_level": "low"},
        )
        bucket["names"].append(roi_name)
        try:
            bucket["temps"].append(float(roi.get("mean_c")))
        except Exception:
            pass
        try:
            bucket["counts"].append(int(roi.get("count") or 0))
        except Exception:
            pass

    if not section_buckets:
        section_buckets["综合评估"] = {"names": [summary], "temps": [], "counts": [], "risk_level": analysis.get("risk_level", "unknown")}

    risk_summary_rows: List[Dict[str, Any]] = []
    section_id = 1
    for section_name, bucket in section_buckets.items():
        names = bucket.get("names") or []
        counts = bucket.get("counts") or []
        score = _risk_score_from_level(analysis.get("risk_level"))
        risk_summary_rows.append(
            {
                "ID": section_id,
                "部位": section_name,
                "风险分值": score,
                "风险等级": _risk_level_cn(analysis.get("risk_level")),
                "你的风险": f"{score}",
                "说明": "；".join(str(item) for item in names[:3]) or summary,
                "特征面积": str(sum(counts)) if counts else "-",
            }
        )
        section_id += 1

    metabolic_rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(abnormal_regions, start=1):
        region_name = _text(item.get("region_cn") or item.get("region"))
        status = str(item.get("status") or "").lower()
        metabolic_rows.append(
            {
                "ID": idx,
                "异常类型": "异常高温" if status == "high" else "异常低温",
                "部位": region_name,
                "面积": _text(item.get("count") or item.get("area") or "-"),
                "均温": _to_temp_text(item.get("avg_c")),
                "温差": _to_temp_text(item.get("delta_c")),
            }
        )

    objective_temp_rows: List[Dict[str, Any]] = []
    for idx, roi in enumerate(roi_list, start=1):
        if not isinstance(roi, dict):
            continue
        roi_name = _text(roi.get("name"), "")
        if not roi_name:
            continue
        objective_temp_rows.append(
            {
                "ID": idx,
                "分组": _section_name(roi_name),
                "部位": roi_name,
                "温度": _to_temp_text(roi.get("mean_c")),
                "最低": _to_temp_text(roi.get("min_c")),
                "最高": _to_temp_text(roi.get("max_c")),
            }
        )

    section_detail_rows: List[Dict[str, Any]] = []
    for idx, roi in enumerate(roi_list, start=1):
        if not isinstance(roi, dict):
            continue
        roi_name = _text(roi.get("name"), "")
        if not roi_name:
            continue
        section_detail_rows.append(
            {
                "ID": idx,
                "章节": _section_name(roi_name),
                "项目": roi_name,
                "热源描述": f"{roi_name}温度分布见热区变化",
                "评估提示": doctor_opinion,
                "热特征度": _severity_from_delta(roi.get("std_c")),
                "面积": _text(roi.get("count") or "-"),
                "对称性": _text(roi.get("symmetry") or "-"),
                "均值": _to_temp_text(roi.get("mean_c")),
                "相对值": _to_temp_text(roi.get("max_c")),
                "标准差": _to_temp_text(roi.get("std_c")),
            }
        )

    advice_rows: List[Dict[str, Any]] = []
    advice_lines = _split_advice_lines(
        report.get("doctor_opinion"),
        (report.get("treatment_plan") or {}).get("ai_recommendation"),
        (report.get("ai") or {}).get("report_note"),
    )
    for idx, line in enumerate(advice_lines, start=1):
        advice_rows.append(
            {
                "ID": idx,
                "章节": "保健建议",
                "项目": f"建议{idx}",
                "建议": line,
            }
        )

    return [
        (
            "exam",
            {
                "单位名称": string_type,
                "createdate": string_type,
                "检查项目名称": string_type,
                "报告编码": string_type,
                "医师名称": string_type,
            },
            exam_rows,
        ),
        (
            "person",
            {"患者名称": string_type, "性别": string_type, "年龄": string_type},
            person_rows,
        ),
        (
            "imgtemprs",
            {"Name": string_type, "Aver": string_type, "Max": string_type, "Min": string_type},
            imgtemprs_rows,
        ),
        (
            "qsimgs",
            {"Line": int_type, "BigFileBlob1": array_type, "FileBlob1": array_type},
            qsimgs_rows,
        ),
        (
            "qsgroup1",
            {"ID": int_type, "级别": int_type, "项目名称": string_type},
            qsgroup1_rows,
        ),
        (
            "qsgroup2",
            {"Id": int_type, "PID": int_type, "项目名称": string_type},
            qsgroup2_rows,
        ),
        (
            "qsgroup3",
            {"Id": int_type, "PID": int_type, "项目名称": string_type},
            qsgroup3_rows,
        ),
        (
            "qslist",
            {
                "ID": int_type,
                "PID": int_type,
                "项目名称": string_type,
                "图像提示": string_type,
                "建议": string_type,
            },
            qslist_rows,
        ),
        (
            "cover",
            {
                "编号": string_type,
                "姓名": string_type,
                "性别": string_type,
                "年龄": string_type,
                "日期": string_type,
                "单位名称": string_type,
                "系统名称": string_type,
                "报告标题": string_type,
                "英文标题": string_type,
            },
            cover_rows,
        ),
        (
            "risk_summary",
            {
                "ID": int_type,
                "部位": string_type,
                "风险分值": int_type,
                "风险等级": string_type,
                "你的风险": string_type,
                "说明": string_type,
                "特征面积": string_type,
            },
            risk_summary_rows,
        ),
        (
            "metabolic_regions",
            {
                "ID": int_type,
                "异常类型": string_type,
                "部位": string_type,
                "面积": string_type,
                "均温": string_type,
                "温差": string_type,
            },
            metabolic_rows,
        ),
        (
            "objective_temp",
            {
                "ID": int_type,
                "分组": string_type,
                "部位": string_type,
                "温度": string_type,
                "最低": string_type,
                "最高": string_type,
            },
            objective_temp_rows,
        ),
        (
            "section_detail",
            {
                "ID": int_type,
                "章节": string_type,
                "项目": string_type,
                "热源描述": string_type,
                "评估提示": string_type,
                "热特征度": string_type,
                "面积": string_type,
                "对称性": string_type,
                "均值": string_type,
                "相对值": string_type,
                "标准差": string_type,
            },
            section_detail_rows,
        ),
        (
            "health_advice",
            {
                "ID": int_type,
                "章节": string_type,
                "项目": string_type,
                "建议": string_type,
            },
            advice_rows,
        ),
    ]


def _create_table(
    data_table_cls,
    name: str,
    columns: Dict[str, Any],
    rows: Iterable[Dict[str, Any]],
    dbnull,
):
    table = data_table_cls(name)
    for col_name, col_type in columns.items():
        table.Columns.Add(col_name, col_type)
    for row in rows:
        data_row = table.NewRow()
        for col_name in columns.keys():
            value = row.get(col_name)
            if value is None:
                value = dbnull.Value
            data_row[col_name] = value
        table.Rows.Add(data_row)
    return table


def generate_template_report(
    report: Dict[str, Any],
    emr: Dict[str, Any],
    template_name: Optional[str] = None,
) -> Path:
    template_path = _select_template(report, template_name)
    if not template_path.exists():
        raise FileNotFoundError(f"模板不存在: {template_path}")

    Report, PDFSimpleExport, DataSet, DataTable, Array, Byte, DBNull, Int32, String = _load_fastreport()

    created_at = report.get("created_at") or emr.get("created_at")
    created_dt = _parse_datetime(created_at)
    date_dir = REPORTS_DIR / created_dt.strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    patient = report.get("patient") or emr.get("patient") or {}
    patient_name = _safe_name(str(patient.get("name") or "患者")) or "患者"
    output_path = date_dir / f"{patient_name}{created_dt.strftime('%Y%m%d%H%M%S')}.pdf"

    data_set = DataSet("frxData")
    tables = _build_tables(report, emr, Array[Byte], Int32, String)
    for name, columns, rows in tables:
        data_set.Tables.Add(_create_table(DataTable, name, columns, rows, DBNull))

    frx_report = Report()
    frx_report.Load(str(template_path))
    frx_report.RegisterData(data_set, "frxData")

    for name, _, _ in tables:
        try:
            data_source = frx_report.GetDataSource(name)
            if data_source is not None:
                data_source.Enabled = True
        except Exception:
            continue

    doctor = (report.get("clinical") or {}).get("doctor") or (report.get("clinical") or {}).get("doctor_name") or ""
    tel = (report.get("clinical") or {}).get("phone") or ""
    try:
        frx_report.SetParameterValue("评估医师", doctor)
        frx_report.SetParameterValue("电话", tel)
    except Exception:
        pass

    frx_report.Prepare()
    exporter = PDFSimpleExport()
    frx_report.Export(exporter, str(output_path))

    return output_path
