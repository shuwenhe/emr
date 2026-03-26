from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from typing import List

from models.schemas.api import AnalyzeRequest, DeviceIngestRequest, DispatchRequest, IngestMetadata
from service.ai import AIService
from service.analysis import AnalysisService
from service.emr import EMRService
from service.ingestion import IngestionService
from service.treatment import TreatmentService
from .events import publish_ingest_progress

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

_DETACHED_INGEST_TASKS: set[asyncio.Task[None]] = set()

ALLOWED_EXTENSIONS = {".csv", ".dat"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
MAX_FILE_MB = 100
ai_service = AIService()
analysis_service = AnalysisService()
ingestion_service = IngestionService()
emr_service = EMRService()
treatment_service = TreatmentService()


def _strip_numeric_citations(text: str) -> str:
    # Remove inline numeric references like [2], [5] from display text.
    cleaned = re.sub(r"\[\d+\]", "", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _has_report_output(emr_result: dict) -> bool:
    if not isinstance(emr_result, dict):
        return False

    for field in ("pdf_report_path", "docx_report_path"):
        value = str(emr_result.get(field) or "").strip()
        if value:
            return True

    report = emr_result.get("report")
    if isinstance(report, dict):
        for field in ("pdf_report_path", "docx_report_path"):
            value = str(report.get(field) or "").strip()
            if value:
                return True

    return False


def _validate_file(file: UploadFile) -> None:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="unsupported_file_type")


def _validate_size(file_bytes: bytes) -> None:
    max_bytes = MAX_FILE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="file_too_large")


def _persist_ai_result(record_id: str, analysis_result: dict, emr_result: dict, ai_result: dict) -> dict:
    emr_id = str(emr_result.get("emr_id") or "").strip()
    if not emr_id:
        logger.warning("[步骤4] AI结果回写 跳过 record_id=%s: missing emr_id", record_id)
        return emr_result

    analysis_report = analysis_result.get("report") if isinstance(analysis_result, dict) else {}
    emr_report = emr_result.get("report") if isinstance(emr_result, dict) else {}

    merged_report = {}
    if isinstance(analysis_report, dict):
        merged_report.update(analysis_report)
    if isinstance(emr_report, dict):
        merged_report.update(emr_report)

    for field in ("diagnosis", "doctor_opinion", "report_note", "health_advice", "treatment_plan_text", "retrieved_context"):
        value = ai_result.get(field)
        if value:
            if field == "doctor_opinion":
                value = _strip_numeric_citations(str(value))
            merged_report[field] = value

    for field in ("section_queries", "section_retrieval"):
        value = ai_result.get(field)
        if isinstance(value, dict):
            merged_report[field] = value

    for field in (
        "retrieved_items",
        "citations",
        "evidence_item_ids",
        "diagnosis_evidence_item_ids",
        "plan_evidence_item_ids",
        "health_advice_evidence_item_ids",
    ):
        value = ai_result.get(field)
        if isinstance(value, list):
            merged_report[field] = value

    if ai_result.get("model"):
        merged_report["ai_model"] = ai_result["model"]

    updates = {"report": merged_report}
    if ai_result.get("diagnosis"):
        updates["diagnosis"] = ai_result["diagnosis"]
    if ai_result.get("doctor_opinion"):
        updates["doctor_opinion"] = _strip_numeric_citations(str(ai_result["doctor_opinion"]))

    if ai_result.get("treatment_plan_text"):
        treatment_plan = emr_result.get("treatment_plan") if isinstance(emr_result.get("treatment_plan"), dict) else {}
        updates["treatment_plan"] = {
            **treatment_plan,
            "treatment_plan_text": ai_result["treatment_plan_text"],
            "health_advice": ai_result.get("health_advice") or treatment_plan.get("health_advice"),
            "evidence_item_ids": ai_result.get("plan_evidence_item_ids") or ai_result.get("evidence_item_ids") or [],
        }

    updated = emr_service.update_emr(emr_id, updates) or {}
    logger.info(
        "[步骤4] AI结果回写 完成 record_id=%s emr_id=%s citations=%d evidence_ids=%d",
        record_id,
        emr_id,
        len(merged_report.get("citations") or []),
        len(merged_report.get("evidence_item_ids") or []),
    )
    return updated or emr_result


async def _generate_report_after_ingest(record_id: str, metadata: dict | None = None) -> None:
    """完整报告生成流水线：步骤2分析 → 步骤3EMR → 步骤4AI → 步骤5治疗方案"""
    ingest_metadata = metadata if isinstance(metadata, dict) else {}
    patient = ingest_metadata.get("patient") if isinstance(ingest_metadata.get("patient"), dict) else {}
    analysis_result: dict = {}
    emr_result: dict = {}

    # ---- 步骤2：热成像分析 ----
    await publish_ingest_progress(record_id, 2, "正在分析热成像数据...", 15)
    try:
        logger.info("[步骤2] 热成像分析 开始 record_id=%s", record_id)
        t0 = time.time()
        analysis_result = await asyncio.to_thread(analysis_service.analyze_record, record_id) or {}
        elapsed = time.time() - t0
        risk = (analysis_result.get("report") or {}).get("analysis", {}).get("risk_level", "unknown")
        logger.info("[步骤2] 热成像分析 完成 record_id=%s risk_level=%s 耗时=%.2fs", record_id, risk, elapsed)
        await publish_ingest_progress(record_id, 2, f"热成像分析完成（风险：{risk}）", 35, "done")
    except Exception as exc:
        logger.exception("[步骤2] 热成像分析 失败 record_id=%s error=%s", record_id, exc)
        await publish_ingest_progress(record_id, 2, "热成像分析失败", 35, "error")

    # ---- 步骤3：电子病历生成 ----
    await publish_ingest_progress(record_id, 3, "正在生成电子病历...", 40)
    try:
        logger.info("[步骤3] 电子病历生成 开始 record_id=%s", record_id)
        t0 = time.time()
        emr_result = await asyncio.to_thread(
            emr_service.create_emr,
            record_id,
            ensure_report_outputs=False,
        ) or {}
        elapsed = time.time() - t0
        if emr_result:
            logger.info(
                "[步骤3] 电子病历生成 完成 record_id=%s emr_id=%s 耗时=%.2fs",
                record_id, emr_result.get("emr_id"), elapsed,
            )
        else:
            logger.warning("[步骤3] 电子病历生成 返回空结果 record_id=%s", record_id)
        await publish_ingest_progress(record_id, 3, "电子病历生成完成", 55, "done")
    except Exception as exc:
        logger.exception("[步骤3] 电子病历生成 失败 record_id=%s error=%s", record_id, exc)
        await publish_ingest_progress(record_id, 3, "电子病历生成失败", 55, "error")

    # ---- 步骤4：AI报告生成 ----
    await publish_ingest_progress(record_id, 4, "正在生成AI诊断报告...", 60)
    try:
        logger.info("[步骤4] AI报告生成 开始 record_id=%s", record_id)
        t0 = time.time()
        ai_result = await asyncio.to_thread(ai_service.generate_report_summary, analysis_result, emr_result) or {}
        if ai_result and emr_result:
            emr_result = await asyncio.to_thread(_persist_ai_result, record_id, analysis_result, emr_result, ai_result)

        # Even when AI is disabled or returns empty content, we still need
        # report files for history list and preview pages.
        if emr_result and not _has_report_output(emr_result):
            try:
                emr_result = await asyncio.to_thread(
                    emr_service.create_emr,
                    record_id,
                    ensure_report_outputs=True,
                ) or emr_result
                logger.info("[步骤4] AI后报告文件补齐 完成 record_id=%s", record_id)
            except Exception as backfill_exc:
                logger.warning("[步骤4] AI后报告文件补齐失败 record_id=%s error=%s", record_id, backfill_exc)

        elapsed = time.time() - t0
        logger.info("[步骤4] AI报告生成 完成 record_id=%s keys=%s 耗时=%.2fs", record_id, list(ai_result.keys()), elapsed)
        await publish_ingest_progress(record_id, 4, "AI诊断报告生成完成", 80, "done")
    except Exception as exc:
        logger.exception("[步骤4] AI报告生成 失败 record_id=%s error=%s", record_id, exc)
        try:
            emr_result = await asyncio.to_thread(
                emr_service.create_emr,
                record_id,
                ensure_report_outputs=True,
            ) or emr_result
        except Exception as fallback_exc:
            logger.warning("[步骤4] AI失败后补生成基础报告失败 record_id=%s error=%s", record_id, fallback_exc)
        await publish_ingest_progress(record_id, 4, "AI报告生成失败", 80, "error")

    # ---- 步骤5：治疗方案 ----
    await publish_ingest_progress(record_id, 5, "正在制定治疗方案...", 85)
    try:
        logger.info("[步骤5] 治疗方案生成 开始 record_id=%s", record_id)
        t0 = time.time()
        plan = await asyncio.to_thread(treatment_service.generate_treatment_plan, analysis_result, patient) or {}
        elapsed = time.time() - t0
        risk_out = plan.get("risk_level", "unknown")
        logger.info("[步骤5] 治疗方案生成 完成 record_id=%s risk_level=%s 耗时=%.2fs", record_id, risk_out, elapsed)
        await publish_ingest_progress(record_id, 5, "治疗方案生成完成", 95, "done")
    except Exception as exc:
        logger.exception("[步骤5] 治疗方案生成 失败 record_id=%s error=%s", record_id, exc)
        await publish_ingest_progress(record_id, 5, "治疗方案生成失败", 95, "error")

    # ---- 全部完成 ----
    await publish_ingest_progress(record_id, 5, "全部分析完成，正在跳转...", 100, "complete")


def _start_detached_ingest_pipeline(record_id: str, metadata: dict | None = None) -> None:
    task = asyncio.create_task(_generate_report_after_ingest(record_id, metadata))
    _DETACHED_INGEST_TASKS.add(task)

    def _cleanup(done_task: asyncio.Task[None]) -> None:
        _DETACHED_INGEST_TASKS.discard(done_task)
        try:
            done_task.result()
        except Exception:
            logger.exception("[ingest] detached pipeline failed record_id=%s", record_id)

    task.add_done_callback(_cleanup)


@router.post("/ingest")
async def ingest(
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
    record_id = await asyncio.to_thread(
        ingestion_service.ingest_data,
        tmp_file,
        parsed.model_dump(),
        validate=True,
    )
    result = {"record_id": record_id, "storage_path": None, "matrix_csv_path": None}

    # Seed the progress cache (step 1, 5%) so the frontend receives an immediate
    # replay event even if it connects after the background task has already
    # started publishing later steps.
    await publish_ingest_progress(record_id, 1, "数据采集完成，正在启动分析...", 5)

    _start_detached_ingest_pipeline(result["record_id"], parsed.model_dump())

    elapsed = time.time() - t0
    logger.info("[步骤1] 数据采集 完成 record_id=%s 耗时=%.2fs EMR生成已后台调度", record_id, elapsed)
    return {
        **result,
        "qc_issues": [],  # No QC issues if validation passed
        "report_generation": "scheduled",
    }


@router.post("/ingest/batch")
async def ingest_batch(
    files: List[UploadFile] = File(...),
    metadata: str = Form(...),
):
    """
    Batch ingest: upload multiple data files (.dat/.csv) and optional thermal
    images (.jpg/.png) for the same patient and generate a single combined report.

    All files are stored under one record_id.  Report generation runs once in
    the background for that record.
    """
    if not files:
        raise HTTPException(status_code=400, detail="no_files_provided")

    try:
        metadata_json = json.loads(metadata)
        parsed = IngestMetadata.model_validate(metadata_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_metadata") from exc

    # Separate data files from image files
    data_files: list[UploadFile] = []
    image_files_upload: list[UploadFile] = []

    for f in files:
        suffix = Path(f.filename).suffix.lower()
        if suffix in ALLOWED_EXTENSIONS:
            data_files.append(f)
        elif suffix in ALLOWED_IMAGE_EXTENSIONS:
            image_files_upload.append(f)
        else:
            logger.warning("[步骤1-批量] 忽略不支持的文件类型 filename=%s", f.filename)

    if not data_files:
        raise HTTPException(status_code=400, detail="no_supported_data_file_in_batch")

    # Check sizes
    for f in files:
        content = await f.read()
        await f.seek(0)
        if len(content) > MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"file_too_large: {f.filename}")

    # Read primary data file
    primary_upload = data_files[0]
    primary_bytes = await primary_upload.read()
    tmp_primary = Path("/tmp") / primary_upload.filename
    tmp_primary.write_bytes(primary_bytes)

    # Read extra data files
    extra_data: list[tuple] = []
    for extra_upload in data_files[1:]:
        extra_bytes = await extra_upload.read()
        extra_data.append((extra_upload.filename, extra_bytes))

    # Read image files
    image_data: list[tuple] = []
    for img_upload in image_files_upload:
        img_bytes = await img_upload.read()
        image_data.append((img_upload.filename, img_bytes))

    logger.info(
        "[步骤1-批量] 开始 primary=%s extra_data=%d images=%d",
        primary_upload.filename, len(extra_data), len(image_data),
    )
    t0 = time.time()

    try:
        record_id = await asyncio.to_thread(
            ingestion_service.ingest_batch,
            tmp_primary,
            parsed.model_dump(),
            extra_data_files=extra_data or None,
            image_files=image_data or None,
            validate=True,
        )
    except Exception as exc:
        detail = exc.args[0] if exc.args else "ingest_batch_failed"
        raise HTTPException(status_code=422, detail=detail) from exc

    _start_detached_ingest_pipeline(record_id, parsed.model_dump())

    # Seed the progress cache so late-connecting subscribers get an immediate replay.
    await publish_ingest_progress(record_id, 1, "数据采集完成，正在启动分析...", 5)

    elapsed = time.time() - t0
    logger.info(
        "[步骤1-批量] 完成 record_id=%s data_files=%d images=%d 耗时=%.2fs",
        record_id, len(data_files), len(image_data), elapsed,
    )
    return {
        "record_id": record_id,
        "data_files": len(data_files),
        "image_files": len(image_data),
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
    capture_result = ingestion_service.ingest_pending_captures(move_to_processed=request.move_to_processed)
    patient_result = ingestion_service.ingest_pending_patient_folders(move_to_processed=request.move_to_processed)

    result = {
        "ingested": (capture_result.get("ingested", []) if isinstance(capture_result, dict) else [])
        + (patient_result.get("ingested", []) if isinstance(patient_result, dict) else []),
        "skipped": (capture_result.get("skipped", []) if isinstance(capture_result, dict) else [])
        + (patient_result.get("skipped", []) if isinstance(patient_result, dict) else []),
        "capture_ingested": len(capture_result.get("ingested", []) if isinstance(capture_result, dict) else []),
        "patient_folder_ingested": len(patient_result.get("ingested", []) if isinstance(patient_result, dict) else []),
    }
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
