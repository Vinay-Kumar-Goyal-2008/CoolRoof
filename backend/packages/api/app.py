"""FastAPI application factory and the Lambda handler (Mangum).

``uvicorn packages.api.app:app`` runs it locally; on AWS, API Gateway invokes
``packages.api.app.handler``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from packages.adapters.registry import Adapters, build_adapters
from packages.api.deps import AppState
from packages.api.errors import install_error_handlers
from packages.api.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from packages.api.routers import agent, health, solar, wards
from packages.core.logging import configure_logging
from packages.core.params import ParamRegistry, load_params
from packages.core.settings import AppSettings, get_settings

__all__ = ["app", "create_app", "handler"]

MAX_BODY_BYTES = 2 * 1024 * 1024


def create_app(
    settings: AppSettings | None = None,
    adapters: Adapters | None = None,
    params: ParamRegistry | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings / adapters."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    state = AppState(
        settings=settings,
        adapters=adapters or build_adapters(settings),
        params=params or load_params(settings.config_dir / "params.default.yaml"),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.adapters.scheduler.start()
        yield
        state.adapters.scheduler.shutdown()

    app = FastAPI(
        title="CoolRoof API",
        version="1",
        summary="CoolRoof Planner + Heat Intelligence + SuryaCheck",
        lifespan=lifespan,
    )
    app.state.coolroof = state

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "X-Session-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    for r in (health.router, wards.router, solar.router, agent.router):
        app.include_router(r)
    return app


app = create_app()
handler = Mangum(app, lifespan="off")
