"""Structured JSON logging configuration for Bulk Certificate Generator."""

import json
import logging
import sys
from datetime import datetime, timezone
from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    """Custom logging formatter outputting valid JSON records."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_payload)


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = JsonFormatter()
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
