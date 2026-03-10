from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sys

# Import from new core configuration
from src.backend.core.config import settings
from src.backend.core.logging import get_logger

logger = get_logger(__name__)
DATA_DIR = settings.DATA_DIR
DEFAULT_REPORT_TEMPLATE = settings.DEFAULT_REPORT_TEMPLATE
REPORTS_DIR = settings.REPORTS_DIR
TEMPLATE_DIR = settings.TEMPLATE_DIR


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

    marked_image = _resolve_image_path(report.get("thermal_marked_image"))
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
    emr_id = str(emr.get("emr_id") or report.get("report_id") or "")
    emr_suffix = f"_{_safe_name(emr_id)}" if emr_id else ""
    output_path = date_dir / f"{patient_name}_{created_dt.strftime('%Y%m%d_%H%M%S')}{emr_suffix}.pdf"

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
