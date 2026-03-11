"""Deprecated compatibility layer for report generation.

Canonical implementation lives under ``reports.python``.
"""

from reports.python import generate_docx_report, generate_template_report

__all__ = ["generate_docx_report", "generate_template_report"]
