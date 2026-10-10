"""Structured JSON logging with request/run IDs and PII scrubbing (M42)."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

__all__ = ["bind_context", "clear_context", "configure_logging", "get_logger"]

# Keys that may hold personal data; their values never reach the logs.
_PII_KEYS = frozenset(
    {"name", "applicant_name", "address", "email", "phone", "mobile", "aadhaar", "bank_account"}
)


def _scrub_pii(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in _PII_KEYS:
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO", *, json: bool = True) -> None:
    """Configure structlog once per process."""
    renderer: Any = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _scrub_pii,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)


def bind_context(**values: Any) -> None:
    """Bind e.g. ``request_id`` / ``run_id`` for every log line in this context."""
    structlog.contextvars.bind_contextvars(**values)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
