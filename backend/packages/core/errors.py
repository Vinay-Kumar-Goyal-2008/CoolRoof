"""Error hierarchy mapped to the API error codes in §4.5.

Every error the API can return is a ``CoolRoofError`` subclass carrying its HTTP
status. Names avoid shadowing ``pydantic.ValidationError`` and the built-in
``TimeoutError``.
"""

from __future__ import annotations

from typing import Any, ClassVar

__all__ = [
    "AuthenticationError",
    "ConflictError",
    "CoolRoofError",
    "ForbiddenError",
    "IncompleteError",
    "InputValidationError",
    "NotFoundError",
    "ParameterUnavailableError",
    "PolicyUnavailableError",
    "ThrottledError",
    "UpstreamError",
    "UpstreamTimeoutError",
]


class CoolRoofError(Exception):
    """Base class. ``status_code`` is the HTTP status used by the API layer."""

    status_code: ClassVar[int] = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InputValidationError(CoolRoofError):
    """400 — request failed validation."""

    status_code = 400


class AuthenticationError(CoolRoofError):
    """401 — no or invalid credentials."""

    status_code = 401


class ForbiddenError(CoolRoofError):
    """403 — authenticated but the role lacks the capability."""

    status_code = 403


class NotFoundError(CoolRoofError):
    """404 — outside coverage or unknown id."""

    status_code = 404


class ConflictError(CoolRoofError):
    """409 — run in progress / already approved."""

    status_code = 409


class IncompleteError(CoolRoofError):
    """422 — input incomplete or output withheld."""

    status_code = 422


class PolicyUnavailableError(CoolRoofError):
    """424 — a required policy record is missing or stale."""

    status_code = 424


class ThrottledError(CoolRoofError):
    """429 — rate limit or session cap reached."""

    status_code = 429


class UpstreamError(CoolRoofError):
    """502 — an upstream source failed and nothing could be returned."""

    status_code = 502


class UpstreamTimeoutError(CoolRoofError):
    """504 — timed out; the call is idempotent and may be retried."""

    status_code = 504


class ParameterUnavailableError(CoolRoofError):
    """A P-* parameter has no value (``null`` / [NV]); callers degrade to ``unavailable``."""

    status_code = 422

    def __init__(self, param_id: str) -> None:
        super().__init__(f"parameter {param_id} has no value", details={"param_id": param_id})
        self.param_id = param_id
