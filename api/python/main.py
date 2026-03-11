"""Compatibility shim.

Primary Python API implementation now lives under `route/python/main.py`.
"""

from __future__ import annotations

from route.python.main import app

__all__ = ["app"]
