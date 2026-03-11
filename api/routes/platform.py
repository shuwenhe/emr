"""Compatibility shim for platform routes.

Primary Python implementation now lives under `api/python/routes/platform.py`.
"""

from __future__ import annotations

from ..python.routes.platform import router

__all__ = ["router"]
