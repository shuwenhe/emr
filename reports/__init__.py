"""Project-local reports package.

Canonical report generation implementation lives in ``reports.python``.
"""

from .python import generate_docx_report, generate_template_report

__all__ = ["generate_docx_report", "generate_template_report"]
