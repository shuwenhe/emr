"""Custom exceptions for EMR system."""

from typing import Any, Optional


class EMRException(Exception):
    """Base exception for EMR system."""
    
    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}


class ConfigurationError(EMRException):
    """Configuration error."""
    pass


class DatabaseError(EMRException):
    """Database operation error."""
    pass


class StorageError(EMRException):
    """File storage error."""
    pass


class ValidationError(EMRException):
    """Data validation error."""
    pass


class NotFoundError(EMRException):
    """Resource not found."""
    pass


class EMRNotFoundError(NotFoundError):
    """EMR record not found."""
    pass


class PatientNotFoundError(NotFoundError):
    """Patient not found."""
    pass


class ReportGenerationError(EMRException):
    """Report generation error."""
    pass


class DeviceConnectionError(EMRException):
    """Device connection error."""
    pass


class AnalysisError(EMRException):
    """Data analysis error."""
    pass


class LLMError(EMRException):
    """LLM service error."""
    pass


__all__ = [
    "EMRException",
    "ConfigurationError",
    "DatabaseError",
    "StorageError",
    "ValidationError",
    "NotFoundError",
    "EMRNotFoundError",
    "PatientNotFoundError",
    "ReportGenerationError",
    "DeviceConnectionError",
    "AnalysisError",
    "LLMError",
]
