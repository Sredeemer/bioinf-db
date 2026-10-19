"""Structured JSON and contextual logging for UbuntuBio services (GCP Cloud Logging ready)."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from ubuntubio.config import settings

# Asynchronous request correlation context variables
request_id_ctx: ContextVar[str | None] = ContextVar("request_id_ctx", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id_ctx", default=None)
repo_slug_ctx: ContextVar[str | None] = ContextVar("repo_slug_ctx", default=None)

# Standard LogRecord attributes to ignore when extracting custom extra fields
_LOG_RECORD_BUILTIN_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class CorrelationFilter(logging.Filter):
    """Injects async context correlation variables into LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id") or record.request_id is None:
            record.request_id = request_id_ctx.get()
        if not hasattr(record, "user_id") or record.user_id is None:
            record.user_id = user_id_ctx.get()
        if not hasattr(record, "repo_slug") or record.repo_slug is None:
            record.repo_slug = repo_slug_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """Outputs structured single-line JSON formatted for Google Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Context correlation fields
        req_id = getattr(record, "request_id", None)
        if req_id:
            payload["request_id"] = req_id

        user_id = getattr(record, "user_id", None)
        if user_id:
            payload["user_id"] = user_id

        repo_slug = getattr(record, "repo_slug", None)
        if repo_slug:
            payload["repo_slug"] = repo_slug

        # Add custom extra fields passed via extra={...}
        for attr, value in record.__dict__.items():
            if attr not in _LOG_RECORD_BUILTIN_ATTRS and attr not in (
                "request_id",
                "user_id",
                "repo_slug",
            ):
                try:
                    json.dumps(value)
                    payload[attr] = value
                except (TypeError, OverflowError):
                    payload[attr] = str(value)

        # Exception formatting
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text

        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter with correlation fields for local console development."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or "-"
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        msg = record.getMessage()
        base = f"[{timestamp}] [{record.levelname:<7}] [{record.name}] [{req_id}] {msg}"

        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def get_logger(name: str) -> logging.Logger:
    """Retrieve a configured logger instance with correlation filter."""
    return logging.getLogger(name)


def setup_logging(
    log_level: str | None = None,
    log_format: str | None = None,
) -> None:
    """Initialize structured application logging across ubuntubio and standard loggers."""
    level_name = (log_level or settings.LOG_LEVEL).upper()
    format_type = (log_format or settings.LOG_FORMAT).lower()
    numeric_level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Console stream handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(numeric_level)
    stream_handler.addFilter(CorrelationFilter())

    if format_type == "json":
        stream_handler.setFormatter(JsonFormatter())
    else:
        stream_handler.setFormatter(TextFormatter())

    root_logger.addHandler(stream_handler)

    # Configure ubuntubio logger specifically
    app_logger = logging.getLogger("ubuntubio")
    app_logger.setLevel(numeric_level)
    app_logger.propagate = True

    # Suppress overly noisy third-party loggers unless in DEBUG
    if numeric_level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("aiosqlite").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
