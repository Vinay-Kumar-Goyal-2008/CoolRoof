from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel

from packages.api.app import create_app
from packages.api.deps import require_role
from packages.core.enums import Role
from packages.core.errors import PolicyUnavailableError
from packages.core.settings import AppSettings


def _client(settings: AppSettings) -> TestClient:
    app = create_app(settings)
    extra = APIRouter()

    class Body(BaseModel):
        kw: float

    @extra.get("/_boom")
    def boom() -> None:
        raise PolicyUnavailableError("subsidy policy is stale")

    @extra.post("/_echo")
    def echo(body: Body) -> Body:
        return body

    @extra.get("/_planner", dependencies=[Depends(require_role(Role.PLANNER))])
    def planner_only() -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(extra)
    return TestClient(app)


def test_health_returns_envelope_with_versions(settings: AppSettings) -> None:
    res = _client(settings).get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["runtime"] == "local"
    assert body["meta"]["request_id"] == res.headers["x-request-id"]


def test_domain_error_maps_to_spec_error_envelope(settings: AppSettings) -> None:
    res = _client(settings).get("/_boom")
    assert res.status_code == 424
    assert res.json()["error"]["code"] == 424


def test_validation_error_is_400(settings: AppSettings) -> None:
    res = _client(settings).post("/_echo", json={"kw": "lots"})
    assert res.status_code == 400
    assert res.json()["error"]["message"] == "request validation failed"


def test_planner_routes_require_api_key(settings: AppSettings) -> None:
    keyed = AppSettings(  # type: ignore[call-arg]
        data_dir=settings.data_dir, planner_api_key="s3cret-planner", _env_file=None
    )
    client = _client(keyed)
    assert client.get("/_planner").status_code == 401  # authentication required
    assert client.get("/_planner", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/_planner", headers={"X-API-Key": "s3cret-planner"}).status_code == 200
