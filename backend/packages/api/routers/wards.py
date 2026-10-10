"""Heat analysis endpoints: wards, ward context, roofs, heat type, recommendations, plan, forecast."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from packages.api.deps import StateDep
from packages.api.envelope import ApiResponse, ok
from packages.api.routers._common import CityQ, repo_of, signals_of
from packages.core.city import load_city
from packages.core.context import WardContext
from packages.core.errors import IncompleteError, NotFoundError
from packages.pipeline.m09_priority import WardScore
from packages.pipeline.m11_coolroof import assess_roofs
from packages.pipeline.m14_actions import build_action_plan
from packages.services.m17_reco import load_rules, recommend

router = APIRouter(tags=["wards"])


@router.get("/wards", response_model=ApiResponse[dict[str, Any]])
def list_wards(request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    repo = repo_of(state)
    manifest = repo.manifest(city)
    items = []
    for doc in repo.wards(city):
        ctx = doc["ward_context"]
        items.append(
            {
                "ward_id": ctx["ward_id"],
                "name": ctx["location"]["name"],
                "name_hi": ctx["location"]["name_hi"],
                "priority": doc["priority"],
                "heat_type": doc["heat_type"],
                "mean_dlst_c": ctx["heat"].get("mean_dlst_c"),
                "population": ctx["population"].get("population"),
                "exposed_population": ctx["population"].get("exposed_population"),
                "degradation_signal": ctx.get("environment", {})
                .get("degradation_signal", {})
                .get("value"),
                "habitat_pressure_max": ctx.get("hazards", {})
                .get("habitat_pressure_max", {})
                .get("value"),
                "fire_events_30d": ctx.get("hazards", {}).get("fire_events_30d", {}).get("value"),
                "hospital_count": ctx.get("infrastructure", {})
                .get("hospital_count", {})
                .get("value"),
                "nearest_hospital_m": ctx.get("infrastructure", {})
                .get("nearest_hospital_m", {})
                .get("value"),
                "heatdome_risk": ctx["heat"].get("heatdome_risk", {}).get("value"),
                "data_quality": ctx["data_quality"],
            }
        )
    geo = repo.blob_json(f"curated/{city}/wards.geojson")
    try:
        hotspots = repo.blob_json(f"curated/{city}/hotspots.geojson")
    except NotFoundError:
        hotspots = None
    return ok(
        {
            "wards": items,
            "geojson": geo,
            "hotspots": hotspots,
            "normalisation": manifest["normalisation"],
            "sensitivity": manifest["sensitivity"],
            "scenes": manifest["scenes"],
            "layers": manifest.get("layers", {}),
            "fire_as_of": manifest.get("fire_as_of"),
            "signals": signals_of(state, city).to_dict(),
        },
        request,
        context_version=manifest["context_version"],
    )


@router.get("/wards/{ward_id}/context", response_model=ApiResponse[dict[str, Any]])
def ward_context(ward_id: str, request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    doc = repo_of(state).ward(city, ward_id)
    return ok(doc["ward_context"], request, context_version=doc["ward_context"]["context_version"])


@router.get("/wards/{ward_id}/heat-type", response_model=ApiResponse[dict[str, Any]])
def heat_type(ward_id: str, request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    repo = repo_of(state)
    doc = repo.ward(city, ward_id)
    rules = load_rules(state.settings.rules_dir, state.settings.rules_version)
    htype = doc["heat_type"]
    brief = rules.briefs.get(htype["type"], {})
    return ok(
        {
            **htype,
            "brief": brief,
            "label_note": "Heat type is rule-based on surface temperature at a late-morning satellite pass",
        },
        request,
    )


@router.get("/wards/{ward_id}/buildings", response_model=ApiResponse[dict[str, Any]])
def ward_buildings(
    ward_id: str,
    request: Request,
    state: StateDep,
    city: CityQ = "mini_city",
    top: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Any:
    repo = repo_of(state)
    ward = repo.ward(city, ward_id)
    if "buildings_incomplete" in ward["ward_context"]["data_quality"]["flags"]:
        raise IncompleteError("roof ranking is withheld: building footprints are incomplete here")
    roofs = repo.roofs(ward_id, top)
    items = [
        {
            "building_id": r["roof_context"]["building_id"],
            "rank": r["benefit_rank"],
            "area_m2": r["roof_context"]["area"]["value"],
            "geometry": r["roof_context"]["geometry"],
            "eligible": r["roof_context"]["eligible"],
            "assessment": r["assessment"],
        }
        for r in roofs
        if r["roof_context"]["eligible"]
    ]
    return ok(
        {
            "ward_id": ward_id,
            "basis": "benefit_only"
            if items and items[0]["assessment"]["cost_inr"] is None
            else "benefit_per_rupee",
            "roofs": items,
        },
        request,
    )


@router.get("/buildings/{building_id}/context", response_model=ApiResponse[dict[str, Any]])
def building_context(building_id: str, ward: str, request: Request, state: StateDep) -> Any:
    doc = repo_of(state).roof(ward, building_id)
    return ok({**doc["roof_context"], "assessment": doc["assessment"]}, request)


@router.get("/wards/{ward_id}/recommendations", response_model=ApiResponse[dict[str, Any]])
def recommendations(
    ward_id: str,
    request: Request,
    state: StateDep,
    city: CityQ = "mini_city",
    lang: Annotated[str, Query(pattern="^(en|hi)$")] = "en",
) -> Any:
    repo = repo_of(state)
    docs = repo.wards(city)
    contexts = [WardContext.model_validate(d["ward_context"]) for d in docs]
    mine = next((d for d in docs if d["ward_context"]["ward_id"] == ward_id), None)
    if mine is None:
        raise NotFoundError(f"ward '{ward_id}' not found")
    rules = load_rules(state.settings.rules_dir, state.settings.rules_version)
    result = recommend(
        ward_id,
        contexts,
        mine["priority"]["priority_pct"],
        mine["heat_type"]["type"],
        rules,
        state.params,
        lang,
        official_warning=signals_of(state, city).official,
    )
    return ok(result, request, context_version=result["context_version"])


class PlanRequest(BaseModel):
    city: str = "mini_city"
    budget_inr: float = Field(gt=0)
    ward_ids: list[str] | None = None


@router.post("/interventions/plan", response_model=ApiResponse[dict[str, Any]])
def intervention_plan(body: PlanRequest, request: Request, state: StateDep) -> Any:
    """Budgeted action list. Needs the coating cost (P-CM2); without it → 422."""
    repo = repo_of(state)
    manifest = repo.manifest(body.city)
    city = load_city(body.city)
    params = city.apply_overrides(state.params)
    wards = repo.wards(body.city)
    scores = [
        WardScore(
            ward_id=d["ward_context"]["ward_id"],
            priority=d["priority"]["priority"],
            need=d["priority"]["need"],
            components=d["priority"]["components"],
            variables_used=d["priority"]["variables_used"],
            score_confidence=d["priority"]["score_confidence"],
            rank=d["priority"]["rank"],
        )
        for d in wards
    ]
    import pandas as pd

    rows = []
    incomplete: set[str] = set()
    for d in wards:
        wid = d["ward_context"]["ward_id"]
        if "buildings_incomplete" in d["ward_context"]["data_quality"]["flags"]:
            incomplete.add(wid)
        for r in repo.roofs(wid):
            rc = r["roof_context"]
            rows.append(
                {
                    "building_id": rc["building_id"],
                    "ward_id": wid,
                    "area_m2": rc["area"]["value"],
                    "pop_b": rc["pop_b"]["value"],
                    "heat_local_c": rc["local_heat"].get("value") or float("nan"),
                    "floors": rc.get("floors_est", {}).get("value")
                    if rc.get("floors_est")
                    else None,
                    "eligible": rc["eligible"],
                }
            )
    frame = pd.DataFrame(rows)
    assessments = assess_roofs(frame, manifest["grid_pixel_area_m2"], params)
    plan = build_action_plan(
        scores,
        assessments,
        body.budget_inr,
        incomplete_wards=incomplete,
        ward_filter=set(body.ward_ids) if body.ward_ids else None,
    )
    return ok({**plan.summary(), "csv": plan.to_csv(), "csv_hash": plan.csv_hash}, request)


@router.get("/forecast/heatdome", response_model=ApiResponse[dict[str, Any]])
def heatdome(request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    forecast = repo_of(state).manifest(city).get("forecast")
    if not forecast:
        raise NotFoundError("no heat-dome forecast on record")
    return ok(forecast, request, warnings=["Forecast signal, not an official warning"])
