"""``GET /health`` (M42): liveness plus the versions every output is tagged with."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from pydantic import BaseModel

from packages.api.deps import StateDep
from packages.api.envelope import ApiResponse, ok
from packages.core.ids import record_hash

router = APIRouter(tags=["health"])


def engine_version() -> str:
    try:
        return version("coolroof")
    except PackageNotFoundError:
        return "0.0.0-dev"


class Health(BaseModel):
    status: str
    runtime: str
    engine_version: str
    rules_version: str
    params_hash: str


@router.get("/health", response_model=ApiResponse[Health])
def health(request: Request, state: StateDep) -> ApiResponse[Health]:
    return ok(
        Health(
            status="ok",
            runtime=state.settings.runtime.value,
            engine_version=engine_version(),
            rules_version=state.settings.rules_version,
            params_hash=record_hash(state.params.snapshot()),
        ),
        request,
    )
