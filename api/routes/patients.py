"""Compatibility shim for patients routes.

Primary Python implementation now lives under `api/python/routes/patients.py`.
"""

from __future__ import annotations

from ..python.routes.patients import router

__all__ = ["router"]
