from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from models.schemas.api import AnalyzeRequest, DeviceIngestRequest, DispatchRequest, IngestMetadata
from services.ai import AIService
from services.analysis import AnalysisService
from services.emr import EMRService
from services.ingestion import IngestionService
from services.treatment import TreatmentService

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".dat"}
MAX_FILE_MB = 100
ai_service = AIService()
analysis_service = AnalysisService()
ingestion_service = IngestionService()
emr_service = EMRService()
treatment_service = TreatmentService()


def _validate_file(file: UploadFile) -> None:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported_file_type")


def _validate_size(file_bytes: bytes) -> None:
    max_bytes = MAX_FILE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="file_too_large")


def _generate_report_after_ingest(record_id: str, metadata: dict | None = None) -> None:
    """完整报告生成流水线：步骤2分析 → 步骤3EMR → 步骤4AI → 步骤5治疗方案"""
    patient = metadata or {}
    analysis_result: dict = {}
    emr_result: dict = {}

    # ---- 步骤2：热成像分析 ----
    try:
        logger.info("[步骤2] 热成像分析 开始 record_id=%s", record_id)
        t0 = time.time()
        analysis_result = analysis_service.analyze_record(record_id) or {}
        elapsed = time.time() - t0
        risk = (analysis_result.get("report") or {}).get("analysis", {}).get("risk_level", "unknown")
        logger.info("[步骤2] 热成像分析 完成 record_id=%s risk_level=%s 耗时=%.2fs", record_id, risk, elapsed)
    except Exception as exc:
        logger.exception("[步骤2] 热成像分析 失败 record_id=%s error=%s", record_id, exc)

    # ---- 步骤3：电子病历生成 ----
    try:
        logger.info("[步骤3] 电子病历生成 开始 record_id=%s", record_id)
        t0 = time.time()
        emr_result = emr_service.create_emr(record_id) or {}
        elapsed = time.time() - t0
        if emr_result:
            logger.info(
                "[步骤3] 电子病历生成 完成 record_id=%s emr_id=%s 耗时=%.2fs",
                record_id, emr_result.get("emr_id"), elapsed,
            )
        else:
            logger.warning("[步骤3] 电子病历生成 返回空结果 record_id=%s", record_id)
    except Exception as exc:
        logger.exception("[步骤3] 电子病历生成 失败 record_id=%s error=%s", record_id, exc)

    # ---- 步骤4：AI报告生成 ----
    try:
        logger.info("[步骤4] AI报告生成 开始 record_id=%s", record_id)
        t0 = time.time()
        ai_result = ai_service.generate_report_summary(analysis_result, emr_result) or {}
        elapsed = time.time() - t0
        logger.info("[步骤4] AI报告生成 完成 record_id=%s keys=%s 耗时=%.2fs", record_id, list(ai_result.keys()), elapsed)
    except Exception as exc:
        logger.exception("[步骤4] AI报告生成 失败 record_id=%s error=%s", record_id, exc)

    # ---- 步骤5：治疗方案 ----
    try:
        logger.info("[步骤5] 治疗方案生成 开始 record_id=%s", record_id)
        t0 = time.time()
        plan = treatment_service.generate_treatment_plan(analysis_result, patient) or {}
        elapsed = time.time() - t0
        risk_out = plan.get("risk_level", "unknown")
        logger.info("[步骤5] 治疗方案生成 完成 record_id=%s risk_level=%s 耗时=%.2fs", record_id, risk_out, elapsed)
    except Exception as exc:
        logger.exception("[步骤5] 治疗方案生成 失败 record_id=%s error=%s", record_id, exc)


@router.post("/ingest")
async def ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form(...),
):
    logger.info("[步骤1] 数据采集 开始 filename=%s", file.filename)
    t0 = time.time()
    _validate_file(file)

    try:
        metadata_json = json.loads(metadata)
        parsed = IngestMetadata.model_validate(metadata_json)
    except Exception as exc:
        logger.warning("[步骤1] 数据采集 元数据解析失败 filename=%s error=%s", file.filename, exc)
        raise HTTPException(status_code=400, detail="invalid_metadata") from exc

    file_bytes = await file.read()
    file_size_kb = len(file_bytes) / 1024
    logger.info("[步骤1] 数据采集 文件大小=%.1fKB patient=%s", file_size_kb, parsed.name if hasattr(parsed, 'name') else '未知')
    _validate_size(file_bytes)

    tmp_file = Path("/tmp") / file.filename
    tmp_file.write_bytes(file_bytes)
    record_id = ingestion_service.ingest_data(tmp_file, parsed.model_dump(), validate=True)
    result = {"record_id": record_id, "storage_path": None, "matrix_csv_path": None}
    background_tasks.add_task(_generate_report_after_ingest, result["record_id"], parsed.model_dump())

    elapsed = time.time() - t0
    logger.info("[步骤1] 数据采集 完成 record_id=%s 耗时=%.2fs EMR生成已后台调度", record_id, elapsed)
    return {
        **result,
        "qc_issues": [],  # No QC issues if validation passed
        "report_generation": "scheduled",
    }


@router.post("/device/ingest")
def ingest_from_device(request: DeviceIngestRequest):
    if request.capture_path:
        logger.info("[步骤1] 设备数据采集 开始 capture_path=%s", request.capture_path)
        t0 = time.time()
        try:
            result = ingestion_service.ingest_capture_dir(request.capture_path, move_to_processed=request.move_to_processed)
            elapsed = time.time() - t0
            ingested = len(result.get("ingested", [])) if isinstance(result, dict) else 0
            logger.info("[步骤1] 设备数据采集 完成 ingested=%d 耗时=%.2fs", ingested, elapsed)
            return result
        except FileNotFoundError as exc:
            logger.warning("[步骤1] 设备数据采集 路径不存在 capture_path=%s", request.capture_path)
            raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else "capture_path_not_found")) from exc
        except Exception as exc:
            logger.exception("[步骤1] 设备数据采集 失败 capture_path=%s error=%s", request.capture_path, exc)
            raise HTTPException(status_code=400, detail="capture_ingest_failed") from exc

    logger.info("[步骤1] 设备数据采集 处理所有待导入目录")
    t0 = time.time()
    result = ingestion_service.ingest_pending_captures(move_to_processed=request.move_to_processed)
    elapsed = time.time() - t0
    ingested = len(result.get("ingested", [])) if isinstance(result, dict) else 0
    logger.info("[步骤1] 设备数据采集 批量完成 ingested=%d 耗时=%.2fs", ingested, elapsed)
    return result


@router.post("/analyze")
def analyze(request: AnalyzeRequest):
    logger.info("[步骤2] 热成像分析 开始 record_id=%s", request.record_id)
    t0 = time.time()
    try:
        result = analysis_service.analyze_record(request.record_id)
        elapsed = time.time() - t0
        risk = (result.get("report") or {}).get("analysis", {}).get("risk_level", "unknown") if isinstance(result, dict) else "unknown"
        logger.info("[步骤2] 热成像分析 完成 record_id=%s risk_level=%s 耗时=%.2fs", request.record_id, risk, elapsed)
        return result
    except FileNotFoundError as exc:
        logger.warning("[步骤2] 热成像分析 记录不存在 record_id=%s", request.record_id)
        detail = exc.args[0] if exc.args else "record_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/dispatch")
def dispatch(request: DispatchRequest):
    logger.info("[步骤6] 设备下发 开始 record_id=%s", request.record_id)
    t0 = time.time()
    try:
        result = treatment_service.dispatch_to_device({"record_id": request.record_id}, device_id="default")
        elapsed = time.time() - t0
        dispatch_id = (result.get("dispatch") or {}).get("dispatch_id", "") if isinstance(result, dict) else ""
        status = (result.get("ack") or {}).get("status", "unknown") if isinstance(result, dict) else "unknown"
        logger.info("[步骤6] 设备下发 完成 record_id=%s dispatch_id=%s status=%s 耗时=%.2fs", request.record_id, dispatch_id, status, elapsed)
        return result
    except FileNotFoundError as exc:
        logger.warning("[步骤6] 设备下发 记录不存在 record_id=%s", request.record_id)
        detail = exc.args[0] if exc.args else "dispatch_not_found"
        raise HTTPException(status_code=404, detail=detail) from exc
