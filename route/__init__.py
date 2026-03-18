from .emr import router as emr_router
from .ingest import router as ingest_router
from .patients import router as patients_router
from .platform import router as platform_router
from .reports import router as reports_router
from .notifications import router as notifications_router
from .events import router as events_router

__all__ = [
    "ingest_router",
    "emr_router",
    "patients_router",
    "platform_router",
    "reports_router",
    "notifications_router",
    "events_router",
]
