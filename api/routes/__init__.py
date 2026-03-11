"""Compatibility shim for route imports.

Primary Python routes now live under `api/python/routes`.
"""

from ..python.routes.emr import router as emr_router
from ..python.routes.ingest import router as ingest_router
from ..python.routes.patients import router as patients_router
from ..python.routes.platform import router as platform_router
from ..python.routes.reports import router as reports_router

__all__ = [
    "ingest_router",
    "emr_router",
    "patients_router",
    "platform_router",
    "reports_router",
]
