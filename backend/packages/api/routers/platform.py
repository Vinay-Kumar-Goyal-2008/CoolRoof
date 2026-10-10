"""Locations (M1+2), analysis runs, map layers/tiles, metrics (M42)."""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from packages.api.deps import Principal, StateDep, require_role
from packages.api.envelope import ApiResponse, ok
from packages.api.routers._common import CityQ, repo_of
from packages.core.city import load_city
from packages.core.enums import Role
from packages.core.errors import InputValidationError, NotFoundError
from packages.core.logging import get_logger
from packages.pipeline.inputs import CityInputs
from packages.pipeline.m01_location import WardLayer, build_ward_layer
from packages.services.analysis import claim_run, get_run, run_and_persist

router = APIRouter(tags=["platform"])
Planner = Annotated[Principal, Depends(require_role(Role.PLANNER))]
_log = get_logger("api.platform")


# ---------------------------------------------------------------------------- locations
@lru_cache(maxsize=8)
def _layer(city: str) -> WardLayer:
    cfg = load_city(city)
    inputs = CityInputs(cfg)
    return build_ward_layer(cfg, inputs.wards, inputs.boundary_version)


class ResolveIn(BaseModel):
    city: str = "mini_city"
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=200)
    polygon: dict[str, Any] | None = None


def _resolve(body: ResolveIn) -> dict[str, Any]:
    try:
        layer = _layer(body.city)
    except FileNotFoundError as exc:
        raise NotFoundError(f"unknown city '{body.city}'") from exc
    if body.polygon is not None:
        ref = layer.by_polygon(body.polygon)
    elif body.lat is not None and body.lon is not None:
        ref = layer.by_point(body.lon, body.lat)
    elif body.name:
        ref = layer.by_name(body.name)
    elif body.address:
        ref = layer.by_address(body.address)
    else:
        raise InputValidationError("give lat+lon, a name, an address or a polygon")
    return ref.model_dump(mode="json")


@router.get("/locations/resolve", response_model=ApiResponse[dict[str, Any]])
def resolve_get(
    request: Request,
    city: CityQ = "mini_city",
    lat: float | None = None,
    lon: float | None = None,
    name: str | None = None,
    address: str | None = None,
) -> Any:
    return ok(_resolve(ResolveIn(city=city, lat=lat, lon=lon, name=name, address=address)), request)


@router.post("/locations/resolve", response_model=ApiResponse[dict[str, Any]])
def resolve_post(body: ResolveIn, request: Request) -> Any:
    return ok(_resolve(body), request)


# ---------------------------------------------------------------------------- analysis runs
class AnalysisIn(BaseModel):
    city: str = "mini_city"


def _run_in_thread(state: StateDep, execution: dict[str, Any]) -> None:
    def work() -> None:
        try:
            run_and_persist(
                state.settings, state.adapters, state.params, execution["city"], execution=execution
            )
        except Exception:  # state is already recorded as failed by run_and_persist
            _log.exception("background_analysis_failed")

    threading.Thread(target=work, name=f"analysis-{execution['city']}", daemon=True).start()


@router.post("/analysis/heat", response_model=ApiResponse[dict[str, Any]], status_code=202)
def start_analysis(
    body: AnalysisIn, request: Request, state: StateDep, who: Planner, response: Response
) -> Any:
    """Starts the batch pipeline (202); 409 if one is already running for the city."""
    load_city(body.city)
    execution = claim_run(state.adapters, body.city, who.actor)
    _run_in_thread(state, execution)
    response.headers["Location"] = f"/analysis/heat/{execution['execution_id']}"
    return ok({"execution_id": execution["execution_id"], "state": "running"}, request)


@router.get("/analysis/heat/{execution_id}", response_model=ApiResponse[dict[str, Any]])
def analysis_state(execution_id: str, request: Request, state: StateDep, who: Planner) -> Any:
    doc = get_run(state.adapters, execution_id)
    if doc is None:
        raise NotFoundError("unknown execution id")
    return ok(doc, request)


# ---------------------------------------------------------------------------- layers
@router.get("/layers", response_model=ApiResponse[dict[str, Any]])
def layers(request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    manifest = repo_of(state).manifest(city)
    return ok(
        {
            "layers": manifest.get("layers", {}),
            "tiles_url": f"/tiles/{city}/dlst.pmtiles",
            "fire_as_of": manifest.get("fire_as_of"),
        },
        request,
    )


@router.get("/layers/{city}/{name}.geojson")
def layer_geojson(city: str, name: str, state: StateDep) -> Response:
    if name not in ("facilities", "protected_areas", "hotspots", "wards"):
        raise NotFoundError("unknown layer")
    key = f"curated/{city}/{name}.geojson"
    if not state.adapters.blobstore.exists(key):
        raise NotFoundError("layer not available for this city")
    return Response(state.adapters.blobstore.get(key), media_type="application/geo+json")


@router.get("/tiles/{city}/dlst.pmtiles")
def pmtiles(
    city: str, state: StateDep, range_: Annotated[str | None, Header(alias="range")] = None
) -> Response:
    """PMTiles archive with HTTP Range support (the client reads only the tiles it needs)."""
    if not city.replace("_", "").isalnum():
        raise NotFoundError("unknown city")
    key = f"curated/{city}/dlst.pmtiles"
    if not state.adapters.blobstore.exists(key):
        raise NotFoundError("no ΔLST tiles for this city; run the pipeline")
    data = state.adapters.blobstore.get(key)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"}
    if range_ and range_.startswith("bytes="):
        start_s, _, end_s = range_[6:].partition("-")
        try:
            start = int(start_s) if start_s else max(len(data) - int(end_s), 0)
            end = int(end_s) if end_s and start_s else len(data) - 1
        except ValueError:
            return Response(status_code=416)
        end = min(end, len(data) - 1)
        if start > end or start >= len(data):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
        return Response(
            data[start : end + 1],
            status_code=206,
            media_type="application/octet-stream",
            headers={**headers, "Content-Range": f"bytes {start}-{end}/{len(data)}"},
        )
    return Response(data, media_type="application/octet-stream", headers=headers)
