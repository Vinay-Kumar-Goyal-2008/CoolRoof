"""HTTP middleware: request IDs, structured access logs, body size limit."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from packages.core import metrics
from packages.core.ids import new_uuid
from packages.core.logging import bind_context, clear_context, get_logger

__all__ = ["BodySizeLimitMiddleware", "RequestContextMiddleware"]

_log = get_logger("api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns ``request_id`` (or accepts a safe ``X-Request-ID``) and logs each request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if 8 <= len(incoming) <= 64 and incoming.isalnum() else new_uuid()
        request.state.request_id = request_id
        clear_context()
        bind_context(request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        ms = round((time.perf_counter() - started) * 1000, 1)
        _log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=ms,
        )
        route = getattr(request.scope.get("route"), "path", "unmatched")
        if request.url.path != "/health":
            metrics.emit("LatencyMs", ms, "Milliseconds", Route=route)
            if response.status_code >= 500:
                metrics.emit("Errors5xx", 1, Route=route)
            elif response.status_code >= 400:
                metrics.emit("Errors4xx", 1, Route=route)
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects bodies larger than ``max_bytes`` (spec M39: body size limits)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self._max = max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > self._max:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": 413, "message": "request body too large"}},
            )
        return await call_next(request)
