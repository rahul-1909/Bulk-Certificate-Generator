"""Structured logging configuration for Bulk Certificate Generator."""

import logging
import sys
from app.core.config import get_settings


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    log_format = (
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s"}'
    )

    formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%dT%H:%M:%S%z")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
            handler.setLevel(log_level)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for the specified module name."""
    return logging.getLogger(name)
