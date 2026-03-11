"""Compatibility shim for ingest routes.

Primary Python implementation now lives under `api/python/routes/ingest.py`.
"""

from __future__ import annotations

from .python.ingest import router

__all__ = ["router"]
