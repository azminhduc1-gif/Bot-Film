"""Centralized logging configuration with request/session tracing."""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

# Context-local request/session IDs for tracing without passing them everywhere.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)


class RequestContextFilter(logging.Filter):
    """Inject request/session IDs from context variables into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.session_id = session_id_var.get() or "-"
        return True


def configure_logging(level: str | int = "INFO") -> None:
    """Configure structured logging for the application."""
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [req=%(request_id)s] [sess=%(session_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Reduce noise from third-party libraries.
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the configured context filter already applied."""
    return logging.getLogger(name)


def set_request_context(*, request_id: str | None = None, session_id: str | None = None) -> None:
    """Set context-local IDs for the current async task."""
    if request_id is not None:
        request_id_var.set(request_id)
    if session_id is not None:
        session_id_var.set(session_id)


def clear_request_context() -> None:
    """Clear context-local IDs for the current async task."""
    request_id_var.set(None)
    session_id_var.set(None)
