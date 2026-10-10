"""Advisories + TTS (M18+19), alerts and subscriptions (M37)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from packages.api.deps import Principal, StateDep, get_principal, require_role
from packages.api.envelope import ApiResponse, ok
from packages.api.routers._common import CityQ, advisories_of, hub_of, repo_of, signals_of
from packages.core.enums import Role
from packages.core.errors import InputValidationError, NotFoundError
from packages.services.m18_advisory import ADVISORY_TYPES

router = APIRouter(tags=["advisories"])
Planner = Annotated[Principal, Depends(require_role(Role.PLANNER))]
Anyone = Annotated[Principal, Depends(get_principal)]


class AdvisoryIn(BaseModel):
    city: str = "mini_city"
    ward_id: str | None = None
    type: str = Field(description=f"one of {ADVISORY_TYPES}")
    audience: str | None = Field(default=None, pattern="^(staff|public)$")
    valid_hours: int = Field(default=48, ge=1, le=168)


@router.post("/advisories", response_model=ApiResponse[dict[str, Any]], status_code=201)
def create_advisory(body: AdvisoryIn, request: Request, state: StateDep, who: Planner) -> Any:
    """Compose a bilingual draft from the current signal. An official warning is relayed first."""
    from datetime import timedelta

    from packages.core.timeutil import utc_now

    repo = repo_of(state)
    signals = signals_of(state, body.city)
    if body.ward_id:
        loc = repo.ward(body.city, body.ward_id)["ward_context"]["location"]
        ward_name = {"en": loc["name"], "hi": loc["name_hi"]}
        has_cooling = (
            repo.ward(body.city, body.ward_id)["ward_context"]["infrastructure"]
            .get("cooling_point_count", {})
            .get("value", 0)
            or 0
        ) > 0
    else:
        ward_name = {"en": "the city", "hi": "शहर"}
        has_cooling = False
    if body.type == "heatdome_forecast":
        if signals.forecast_risk in ("unavailable", "none"):
            raise InputValidationError("no heat-dome forecast signal to base an advisory on")
        valid_until = (utc_now() + timedelta(hours=body.valid_hours)).isoformat()
        texts, slots = advisories_of(state).compose(
            advisory_type=body.type,
            ward_name=ward_name,
            valid_until=valid_until,
            risk=signals.forecast_risk,
            has_cooling_point=has_cooling,
        )
    else:
        if signals.official is None:
            raise InputValidationError(
                "no official warning is on record; enter one first (POST /admin/official-warnings)"
            )
        valid_until = signals.official["valid_until"]
        texts, slots = advisories_of(state).compose(
            advisory_type=body.type,
            ward_name=ward_name,
            valid_until=valid_until,
            level=signals.official["level"],
            issued_by=signals.official["issued_by"],
            has_cooling_point=has_cooling,
        )
    doc = advisories_of(state).create(
        city=body.city,
        ward_id=body.ward_id,
        advisory_type=body.type,
        texts=texts,
        slots=slots,
        valid_until=valid_until,
        audience=body.audience,
        created_by=who.actor,
    )
    return ok(doc, request, warnings=["Draft: a planner or admin must approve it before release"])


@router.get("/advisories", response_model=ApiResponse[dict[str, Any]])
def list_advisories(
    request: Request,
    state: StateDep,
    who: Planner,
    city: CityQ = "mini_city",
    status: str | None = None,
) -> Any:
    return ok({"advisories": advisories_of(state).list_advisories(city, status)}, request)


@router.get("/advisories/public", response_model=ApiResponse[dict[str, Any]])
def public_advisories(
    request: Request, state: StateDep, city: CityQ = "mini_city", ward: str | None = None
) -> Any:
    svc = advisories_of(state)
    out = [
        a
        for a in svc.list_advisories(city, "published")
        if a["audience"] == "public"
        and svc.deliverable(a)
        and (ward is None or a["ward_id"] in (None, ward))
    ]
    return ok({"advisories": out}, request)


@router.post("/advisories/{advisory_id}/approve", response_model=ApiResponse[dict[str, Any]])
def approve_advisory(
    advisory_id: str, request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    return ok(advisories_of(state).approve(city, advisory_id, who.actor, who.role.value), request)


@router.post("/advisories/{advisory_id}/publish", response_model=ApiResponse[dict[str, Any]])
def publish_advisory(
    advisory_id: str, request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    return ok(advisories_of(state).publish(city, advisory_id, who.actor), request)


@router.post("/advisories/{advisory_id}/withdraw", response_model=ApiResponse[dict[str, Any]])
def withdraw_advisory(
    advisory_id: str, request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    return ok(advisories_of(state).withdraw(city, advisory_id, who.actor), request)


class TtsIn(BaseModel):
    city: str = "mini_city"
    advisory_id: str
    lang: str = Field(pattern="^(en|hi)$")


@router.post("/tts", response_model=ApiResponse[dict[str, Any]])
def tts(body: TtsIn, request: Request, state: StateDep) -> Any:
    """Audio for an *approved* advisory only (no arbitrary text synthesis)."""
    result = advisories_of(state).audio(body.city, body.advisory_id, body.lang)
    audio = result.get("audio")
    return ok(
        {**result, "audio_url": f"/audio/{audio}" if audio else None},
        request,
        warnings=[] if audio else ["Audio unavailable: showing text only"],
    )


@router.get("/audio/{key:path}")
def audio_file(key: str, state: StateDep) -> Response:
    if not key.startswith("tts/") or ".." in key:
        raise NotFoundError("audio not found")
    ext = key.rsplit(".", 1)[-1]
    return Response(
        state.adapters.blobstore.get(key),
        media_type="audio/mpeg" if ext == "mp3" else "audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------------------- alerts (M37)
@router.get("/alerts", response_model=ApiResponse[dict[str, Any]])
def alerts(
    request: Request,
    state: StateDep,
    who: Anyone,
    city: CityQ = "mini_city",
    ward: str | None = None,
) -> Any:
    staff = who.role.level >= Role.PLANNER.level
    hub = hub_of(state)
    return ok(
        {
            "alerts": hub.active(city, ward, include_staff=staff),
            "drafts": hub.drafts(city) if staff else [],
        },
        request,
    )


@router.post("/alerts/{alert_id}/approve", response_model=ApiResponse[dict[str, Any]])
def approve_alert(
    alert_id: str, request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    hub = hub_of(state)
    hub.approve(city, alert_id, who.actor)
    return ok(hub.send(city, alert_id, who.actor), request)


@router.post("/alerts/{alert_id}/withdraw", response_model=ApiResponse[dict[str, Any]])
def withdraw_alert(
    alert_id: str, request: Request, state: StateDep, who: Planner, city: CityQ = "mini_city"
) -> Any:
    return ok(hub_of(state).withdraw(city, alert_id, who.actor), request)


class SubscribeIn(BaseModel):
    city: str = "mini_city"
    channel: str = Field(pattern="^(email|sms)$")
    address: str = Field(min_length=5, max_length=120)
    ward_ids: list[str] | None = None
    languages: list[str] = ["en"]


@router.post("/alerts/subscriptions", response_model=ApiResponse[dict[str, Any]], status_code=201)
def subscribe(body: SubscribeIn, request: Request, state: StateDep) -> Any:
    sub = hub_of(state).subscribe(
        body.city,
        channel=body.channel,
        address=body.address,
        ward_ids=body.ward_ids,
        languages=body.languages,
    )
    return ok(
        sub,
        request,
        warnings=["Email subscriptions need confirmation; SMS needs sender registration"],
    )


@router.delete(
    "/alerts/subscriptions/{subscription_id}", response_model=ApiResponse[dict[str, Any]]
)
def unsubscribe(
    subscription_id: str, request: Request, state: StateDep, city: CityQ = "mini_city"
) -> Any:
    hub_of(state).unsubscribe(city, subscription_id)
    return ok({"deleted": subscription_id}, request)
