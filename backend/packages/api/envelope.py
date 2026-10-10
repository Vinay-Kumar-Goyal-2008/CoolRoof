"""Standard API response envelope (§4.5): ``{data, meta}`` on success, ``{error}`` on failure."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field

__all__ = ["ApiResponse", "ErrorBody", "ErrorResponse", "Meta", "ok"]


class Meta(BaseModel):
    request_id: str
    context_version: str | None = None
    policy_version: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ApiResponse[T](BaseModel):
    data: T
    meta: Meta


class ErrorBody(BaseModel):
    code: int
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


def request_id_of(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def ok[T](
    data: T,
    request: Request,
    *,
    context_version: str | None = None,
    policy_version: str | None = None,
    warnings: Sequence[str] = (),
) -> ApiResponse[T]:
    """Wrap ``data`` in the success envelope with the request's id."""
    return ApiResponse[T](
        data=data,
        meta=Meta(
            request_id=request_id_of(request),
            context_version=context_version,
            policy_version=policy_version,
            warnings=list(warnings),
        ),
    )
