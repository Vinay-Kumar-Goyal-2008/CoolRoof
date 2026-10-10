"""Heat intelligence: drivers (M16), cooling options (M17), readiness (M20+21), soil (M24)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from packages.api.deps import StateDep
from packages.api.envelope import ApiResponse, ok
from packages.api.routers._common import CityQ, LangQ, repo_of, signals_of
from packages.core.context import WardContext
from packages.core.errors import IncompleteError, NotFoundError
from packages.services.m17_reco import load_rules, matched_cooling
from packages.services.m20_readiness import readiness

router = APIRouter(tags=["heat-intelligence"])


@router.get("/wards/{ward_id}/drivers", response_model=ApiResponse[dict[str, Any]])
def drivers(ward_id: str, request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    doc = repo_of(state).drivers(city, ward_id)
    if doc["status"] != "ok":
        raise IncompleteError(
            f"driver attribution is withheld for this ward: {doc['status']}",
            details={"status": doc["status"]},
        )
    return ok(
        {
            "ward_id": ward_id,
            "drivers": sorted(doc["drivers"], key=lambda d: -abs(d["contribution_c"])),
            "unobserved": doc["unobserved"],
            "model_card": doc["model_card"],
            "wording": doc["wording"],
        },
        request,
        warnings=["Drivers are associated with ward heat; they are not proven causes"],
    )


@router.get("/cooling-options", response_model=ApiResponse[dict[str, Any]])
def cooling_options(
    ward: str, request: Request, state: StateDep, city: CityQ = "mini_city", lang: LangQ = "en"
) -> Any:
    repo = repo_of(state)
    doc = repo.ward(city, ward)
    rules = load_rules(state.settings.rules_dir, state.settings.rules_version)
    ctx = WardContext.model_validate(doc["ward_context"])
    return ok(matched_cooling(ctx, doc["heat_type"]["type"], rules, state.params, lang), request)


@router.get("/wards/{ward_id}/readiness", response_model=ApiResponse[dict[str, Any]])
def ward_readiness(
    ward_id: str, request: Request, state: StateDep, city: CityQ = "mini_city", lang: LangQ = "en"
) -> Any:
    repo = repo_of(state)
    docs = repo.wards(city)
    mine = next((d for d in docs if d["ward_context"]["ward_id"] == ward_id), None)
    if mine is None:
        raise NotFoundError(f"ward '{ward_id}' not found")
    contexts = [WardContext.model_validate(d["ward_context"]) for d in docs]
    result = readiness(
        ward_id,
        contexts,
        mine["heat_type"]["type"],
        signals_of(state, city),
        state.params,
        lang,
    )
    return ok(result, request)


@router.get("/wards/{ward_id}/soil", response_model=ApiResponse[dict[str, Any]])
def soil(ward_id: str, request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    doc = repo_of(state).soil(city, ward_id)
    return ok(doc, request, warnings=["Indicator, not diagnosis"])


@router.get("/forecast/heatdome/history", response_model=ApiResponse[dict[str, Any]])
def heatdome_history(request: Request, state: StateDep, city: CityQ = "mini_city") -> Any:
    return ok({"city": city, "forecasts": repo_of(state).forecast_history(city)}, request)
