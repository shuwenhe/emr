"""
Report generation module.

Provides DOCX and template-based PDF report generation capabilities.
"""

from .docx_generator import generate_docx_report
from .template_generator import generate_template_report

__all__ = ["generate_docx_report", "generate_template_report"]
