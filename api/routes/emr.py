"""Compatibility shim for emr routes.

Primary Python implementation now lives under `api/python/routes/emr.py`.
"""

from __future__ import annotations

from .python.emr import router

__all__ = ["router"]
