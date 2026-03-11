"""Compatibility shim for reports routes.

Primary Python implementation now lives under `api/python/routes/reports.py`.
"""

from __future__ import annotations

from ..python.routes.reports import router

__all__ = ["router"]
