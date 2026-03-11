"""Compatibility shim for legacy entrypoint.

This module keeps `uvicorn app.main:app` working while forwarding all
application wiring to the refactored API entrypoint under `src/backend/api`.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_new_api_main = importlib.import_module("src.backend.api.main")
app = _new_api_main.app


__all__ = ["app"]
