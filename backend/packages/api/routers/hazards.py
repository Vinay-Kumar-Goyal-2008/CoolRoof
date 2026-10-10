"""Hazards: satellite fire events and staff incidents (M22), protected areas (M23)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from shapely.geometry import Point, shape

from packages.api.deps import Principal, StateDep, require_role
from packages.api.envelope import ApiResponse, ok
from packages.api.routers._common import CityQ, hub_of, repo_of
from packages.core.city import load_city
from packages.core.enums import Role
from packages.core.errors import InputValidationError, NotFoundError
from packages.pipeline.inputs import CityInputs
from packages.services.m22_incidents import IncidentService

router = APIRouter(tags=["hazards"])
Planner = Annotated[Principal, Depends(require_role(Role.PLANNER))]


@router.get("/fire/events", response_model=ApiResponse[dict[str, Any]])
def fire_events(
    request: Request,
    state: StateDep,
    city: CityQ = "mini_city",
    since: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    bbox: Annotated[str | None, Query(description="lon0,lat0,lon1,lat1")] = None,
) -> Any:
    events = repo_of(state).fire_events(city, since)
    if bbox:
        try:
            lon0, lat0, lon1, lat1 = (float(v) for v in bbox.split(","))
        except ValueError as exc:
            raise InputValidationError("bbox must be lon0,lat0,lon1,lat1") from exc
        events = [e for e in events if lon0 <= e["lon"] <= lon1 and lat0 <= e["lat"] <= lat1]
    manifest = repo_of(state).manifest(city)
    return ok(
        {
            "events": events,
            "as_of": manifest.get("fire_as_of"),
            "note": "Satellite detections show the last satellite pass, not real time. "
            "Candidate classes are indicative; persistent sources are suppressed from alerts.",
        },
        request,
    )


def _ward_lookup(state: StateDep, city: str) -> Callable[[float, float], str | None]:
    geo = repo_of(state).blob_json(f"curated/{city}/wards.geojson")
    polys = [(f["properties"]["ward_id"], shape(f["geometry"])) for f in geo["features"]]

    def find(lat: float, lon: float) -> str | None:
        pt = Point(lon, lat)
        return next((wid for wid, g in polys if g.contains(pt)), None)

    return find


def _incidents(state: StateDep, city: str) -> IncidentService:
    facilities = CityInputs(load_city(city)).facilities
    rows = (
        [
            {
                "kind": str(r["kind"]),
                "name": str(r["name"]),
                "lat": r.geometry.y,
                "lon": r.geometry.x,
            }
            for _, r in facilities.iterrows()
        ]
        if facilities is not None
        else []
    )
    return IncidentService(
        state.adapters.docstore,
        hub_of(state),
        state.params,
        facilities=rows,
        ward_lookup=_ward_lookup(state, city),
    )


class IncidentIn(BaseModel):
    city: str = "mini_city"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    time: str = Field(description="ISO 8601 time the fire was reported")
    type: str = Field(default="structure_fire", max_length=40)
    source: str = Field(default="staff_report", max_length=60)
    notes: str = Field(default="", max_length=500)


@router.post("/fire/incidents", response_model=ApiResponse[dict[str, Any]], status_code=201)
def log_incident(body: IncidentIn, request: Request, state: StateDep, who: Planner) -> Any:
    repo = repo_of(state)
    events = [e for e in repo.fire_events(body.city) if e.get("acq_date") == body.time[:10]]
    incident = _incidents(state, body.city).report(
        body.city,
        lat=body.lat,
        lon=body.lon,
        occurred_at=body.time,
        kind=body.type,
        source=body.source,
        notes=body.notes,
        reporter=who.actor,
        satellite_events=events,
    )
    return ok(incident, request)


@router.post("/fire/incidents/{incident_id}/confirm", response_model=ApiResponse[dict[str, Any]])
def confirm_incident(
    incident_id: str, request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    return ok(
        _incidents(state, city).confirm(city, incident_id, who.actor),
        request,
        warnings=["A public alert was drafted; it needs approval before it is sent"],
    )


@router.get("/fire/incidents", response_model=ApiResponse[dict[str, Any]])
def list_incidents(
    request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    return ok({"incidents": _incidents(state, city).list_incidents(city)}, request)


@router.get("/protected-areas", response_model=ApiResponse[dict[str, Any]])
def protected_areas(request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    repo = repo_of(state)
    manifest = repo.manifest(city)
    geo = None
    if "protected_areas" in manifest.get("layers", {}):
        geo = repo.blob_json(manifest["layers"]["protected_areas"]["key"])
    return ok({"areas": repo.protected_areas(city), "geojson": geo}, request)


@router.get("/protected-areas/alerts", response_model=ApiResponse[dict[str, Any]])
def protected_area_alerts(
    request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    alerts = [
        {"pa_id": a["pa_id"], "name": a["name"], **w}
        for a in repo_of(state).protected_areas(city)
        for w in a["warnings"]
    ]
    return ok(
        {"alerts": alerts, "audience": "environment and forest officers (not public)"}, request
    )


@router.get("/protected-areas/{pa_id}/pressure", response_model=ApiResponse[dict[str, Any]])
def pressure(pa_id: str, request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    for area in repo_of(state).protected_areas(city):
        if area["pa_id"] == pa_id:
            return ok(area, request, warnings=[area["disclaimer"]])
    raise NotFoundError(f"protected area '{pa_id}' not found")
