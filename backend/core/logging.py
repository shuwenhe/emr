"""Logging configuration for EMR system."""

import logging
import sys
from pathlib import Path
from typing import Optional

from .config import get_settings


def setup_logging(
    name: Optional[str] = None,
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """
    Setup logging configuration.
    
    Args:
        name: Logger name (defaults to root logger)
        level: Log level (defaults to settings.LOG_LEVEL)
        log_file: Path to log file (defaults to settings.LOGS_DIR/app.log)
    
    Returns:
        Configured logger instance
    """
    settings = get_settings()
    
    logger = logging.getLogger(name)
    logger.handlers.clear()
    
    # Set log level
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper())
    logger.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(settings.LOG_FORMAT)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if settings.LOG_TO_FILE:
        if log_file is None:
            log_file = settings.LOGS_DIR / "app.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Setup root logger on module import
setup_logging()


__all__ = ["setup_logging", "get_logger"]
