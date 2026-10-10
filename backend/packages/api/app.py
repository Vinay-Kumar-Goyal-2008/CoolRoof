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
from packages.api.routers import (
    admin,
    advisories,
    agent,
    hazards,
    health,
    heat_intel,
    platform,
    solar,
    wards,
)
from packages.core.logging import configure_logging
from packages.core.params import ParamRegistry, load_params
from packages.core.settings import AppSettings, get_settings
from packages.services.jobs import register_jobs

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
    adapters = adapters or build_adapters(settings)
    state = AppState(
        settings=settings,
        adapters=adapters,
        params=admin.load_overrides(
            params or load_params(settings.config_dir / "params.default.yaml"), adapters.docstore
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.enable_jobs:
            register_jobs(state.adapters, settings, state.params, settings.city)
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
        allow_headers=[
            "Content-Type",
            "X-API-Key",
            "X-Actor",
            "Authorization",
            "X-Request-ID",
            "X-Session-ID",
            "Range",
        ],
        expose_headers=["X-Request-ID", "Content-Range", "Accept-Ranges", "Location"],
    )
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    for r in (
        health.router,
        wards.router,
        heat_intel.router,
        hazards.router,
        advisories.router,
        platform.router,
        admin.router,
        solar.router,
        agent.router,
    ):
        app.include_router(r)
    return app


app = create_app()
handler = Mangum(app, lifespan="off")
