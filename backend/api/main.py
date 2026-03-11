"""API entrypoint for the refactored backend architecture."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymysql.err import OperationalError

from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.services.platform import PlatformService
from .routes import emr_router, ingest_router, patients_router, platform_router, reports_router

setup_logging(__name__)
platform_service = PlatformService()

# Use legacy data directory for static file serving (backward compatibility)
_LEGACY_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_LEGACY_DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Device Ingestion Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/data", StaticFiles(directory=str(_LEGACY_DATA_DIR)), name="data")

app.include_router(ingest_router)
app.include_router(emr_router)
app.include_router(patients_router)
app.include_router(platform_router)
app.include_router(reports_router)

_device_stop_event: asyncio.Event | None = None
logger = logging.getLogger(__name__)


@app.exception_handler(OperationalError)
async def handle_mysql_operational_error(request: Request, exc: OperationalError):
    logger.error("MySQL operational error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "database_unavailable"},
    )


@app.on_event("startup")
async def start_device_polling():
    global _device_stop_event
    _device_stop_event = asyncio.Event()
    try:
        platform_service.init_db()
    except Exception as exc:
        logger.error(
            "MySQL init failed, service starts in degraded mode (device polling disabled). "
            "Check config/mysql.yaml credentials and run database/init_mysql.sql. error=%s",
            exc,
        )
        return
    asyncio.create_task(platform_service.poll_device_drop(_device_stop_event))


@app.on_event("shutdown")
async def stop_device_polling():
    if _device_stop_event is not None:
        _device_stop_event.set()


__all__ = ["app"]
