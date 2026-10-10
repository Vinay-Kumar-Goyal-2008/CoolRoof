"""Maps exceptions to the ``{error:{code,message}}`` envelope."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from packages.api.envelope import ErrorBody, ErrorResponse
from packages.core.errors import CoolRoofError
from packages.core.logging import get_logger

__all__ = ["install_error_handlers"]

_log = get_logger("api.errors")


def _error(code: int, message: str, details: Mapping[str, Any] | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=dict(details or {})))
    return JSONResponse(status_code=code, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CoolRoofError)
    async def _domain(_: Request, exc: CoolRoofError) -> JSONResponse:
        return _error(exc.status_code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # The spec maps validation failures to 400 (not FastAPI's default 422).
        details = {"errors": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}
        return _error(400, "request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        _log.exception("unhandled_error", error=type(exc).__name__)
        return _error(500, "internal error")
