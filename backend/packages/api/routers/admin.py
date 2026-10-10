"""Admin and staff data entry (M41): policy records, parameter overrides, official warnings."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from packages.adapters.docstore import Table
from packages.api.deps import Principal, StateDep, require_role
from packages.api.envelope import ApiResponse, ok
from packages.api.routers._common import CityQ
from packages.core.enums import Role
from packages.core.errors import InputValidationError
from packages.core.params import EvidenceStatus
from packages.core.timeutil import utc_now
from packages.services.policy_store import PolicyStore, PolicyType
from packages.services.signals import LEVELS, OfficialWarnings

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Annotated[Principal, Depends(require_role(Role.ADMIN))]
Planner = Annotated[Principal, Depends(require_role(Role.PLANNER))]

OVERRIDE_PK = "config#params"


class PolicyIn(BaseModel):
    type: PolicyType
    record: dict[str, Any] = Field(
        description="policy document incl. effective_date, source_url, reviewed_on"
    )


@router.put("/policy", response_model=ApiResponse[dict[str, Any]])
def put_policy(body: PolicyIn, request: Request, state: StateDep, who: Admin) -> Any:
    """Versioned by ``effective_date``; older versions are kept. Needs a source and review date."""
    rec = body.record
    for required in ("effective_date", "source_url", "reviewed_on"):
        if not rec.get(required):
            raise InputValidationError(f"policy record needs '{required}'")
    stored = PolicyStore(state.adapters.docstore).put(body.type, {**rec, "type": body.type.value})
    state.adapters.docstore.put(
        Table.CONFIG,
        "audit#policy",
        f"{utc_now().isoformat()}",
        {"by": who.actor, "policy": stored.version, "hash": stored.hash},
    )
    return ok(
        {"policy_version": stored.version, "record_hash": stored.hash},
        request,
        policy_version=stored.version,
    )


class ParamEdit(BaseModel):
    value: Any
    status: EvidenceStatus
    source: str = Field(min_length=3, max_length=300)


class ConfigIn(BaseModel):
    overrides: dict[str, ParamEdit]


def load_overrides(state_params: Any, docs: Any) -> Any:
    """Re-apply stored admin overrides on top of the default registry (called at startup)."""
    rows = docs.query(Table.CONFIG, OVERRIDE_PK)
    merged: dict[str, Any] = {}
    for row in rows:  # ascending: later edits win
        merged.update(row["overrides"])
    return state_params.with_overrides(merged) if merged else state_params


@router.put("/config", response_model=ApiResponse[dict[str, Any]])
def put_config(body: ConfigIn, request: Request, state: StateDep, who: Admin) -> Any:
    """Edit parameter values with their evidence status and source (never a silent change)."""
    for pid in body.overrides:
        if pid not in state.params:
            raise InputValidationError(f"unknown parameter '{pid}'")
    overrides = {
        pid: {"value": e.value, "status": e.status.value, "source": e.source}
        for pid, e in body.overrides.items()
    }
    state.params = state.params.with_overrides(overrides)  # validates the shapes via Param
    version = utc_now().isoformat()
    state.adapters.docstore.put(
        Table.CONFIG, OVERRIDE_PK, version, {"overrides": overrides, "by": who.actor, "at": version}
    )
    return ok({"version": version, "changed": sorted(overrides)}, request)


class WarningIn(BaseModel):
    city: str = "mini_city"
    level: str = Field(description=f"one of {LEVELS}")
    issued_by: str = Field(default="IMD", max_length=60)
    valid_from: str
    valid_until: str
    text: str = Field(max_length=400)
    source_url: str | None = None


@router.post("/official-warnings", response_model=ApiResponse[dict[str, Any]], status_code=201)
def add_warning(body: WarningIn, request: Request, state: StateDep, who: Planner) -> Any:
    """Manual entry of an official (e.g. IMD) heatwave warning. It always outranks the forecast."""
    doc = OfficialWarnings(state.adapters.docstore).add(
        body.city,
        level=body.level,
        issued_by=body.issued_by,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        text=body.text,
        source_url=body.source_url,
        entered_by=who.actor,
    )
    return ok(doc, request)


@router.get("/official-warnings", response_model=ApiResponse[dict[str, Any]])
def list_warnings(
    request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    ow = OfficialWarnings(state.adapters.docstore)
    return ok({"active": ow.active(city), "history": ow.history(city)}, request)


@router.get("/params", response_model=ApiResponse[dict[str, Any]])
def list_params(
    request: Request, state: StateDep, who: Planner, only_unverified: bool = False
) -> Any:
    """Parameters with their evidence status; ``only_unverified`` lists the [NV] gaps."""
    rows = []
    for pid in state.params.ids():
        p = state.params.param(pid)
        if only_unverified and p.status.value != "NV":
            continue
        rows.append(
            {
                "id": pid,
                "value": p.value,
                "unit": p.unit,
                "status": p.status.value,
                "source": p.source,
                "modules": list(p.modules),
            }
        )
    return ok({"params": rows}, request)


@router.get("/metrics", response_model=ApiResponse[dict[str, Any]])
def metrics_snapshot(request: Request, who: Planner) -> Any:
    from packages.core import metrics

    return ok({"metrics": metrics.snapshot()}, request)
