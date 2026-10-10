"""SuryaCheck, policy, checklist and PDF endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel

from packages.api.deps import StateDep
from packages.api.envelope import ApiResponse, ok
from packages.core.enums import Language
from packages.core.errors import NotFoundError
from packages.core.settings import BACKEND_ROOT
from packages.services.m35_pdf import select_checklist
from packages.services.policy_store import PolicyStore, PolicyType
from packages.services.suryacheck import (
    SolarInputs,
    SolarSource,
    SuryaCheckRequest,
    run_suryacheck,
)

router = APIRouter(tags=["solar"])


def solar_inputs(state: StateDep) -> SolarInputs:
    s = state.settings
    fixture = BACKEND_ROOT / "tests" / "fixtures" / "mini_city" / "solar_pvgis.json"
    return SolarInputs(
        state.params,
        PolicyStore(state.adapters.docstore),
        SolarSource(fixture, live=s.solar_source == "live"),
    )


@router.post("/solar/assess", response_model=ApiResponse[dict[str, Any]])
def assess(body: SuryaCheckRequest, request: Request, state: StateDep) -> Any:
    result = run_suryacheck(body, solar_inputs(state))
    return ok(
        result.model_dump(mode="json"),
        request,
        policy_version=result.policy_version,
        warnings=result.warnings,
    )


@router.get("/policy/subsidy", response_model=ApiResponse[dict[str, Any]])
def subsidy_policy(request: Request, state: StateDep, on: date | None = None) -> Any:
    record, level = PolicyStore(state.adapters.docstore).resolve(
        PolicyType.SUBSIDY, state="ALL", discom="ALL", on=on
    )
    if record is None:
        raise NotFoundError("no subsidy policy record")
    return ok(
        {
            **record.doc,
            "policy_version": record.version,
            "record_hash": record.hash,
            "level": level,
        },
        request,
        policy_version=record.version,
    )


@router.get("/checklist", response_model=ApiResponse[dict[str, Any]])
def checklist(
    request: Request,
    state: StateDep,
    state_name: Annotated[str, Query(alias="state")] = "ALL",
    discom: str = "ALL",
) -> Any:
    doc = select_checklist(PolicyStore(state.adapters.docstore), state_name, discom, date.today())
    return ok(doc, request)


class PdfRequest(BaseModel):
    assessment: SuryaCheckRequest
    lang: Language = Language.EN
    consent: bool = False
    name: str | None = None
    address: str | None = None


@router.post("/documents/application-pdf", response_model=ApiResponse[dict[str, Any]])
def application_pdf(body: PdfRequest, request: Request, state: StateDep) -> Any:
    """Raises 424 when the subsidy policy is missing or older than P-HARD-POLICY."""
    import secrets

    from packages.agent.tools import PDF_PREFIX
    from packages.api.routers.health import engine_version
    from packages.services.m35_pdf import build_pdf as _build

    req = body.assessment.model_copy(update={"require_policy": True})
    result = run_suryacheck(req, solar_inputs(state)).model_dump(mode="json")
    consent = (
        {"name": body.name or "", "address": body.address or ""}
        if body.consent and (body.name or body.address)
        else None
    )
    checklist_doc = select_checklist(
        PolicyStore(state.adapters.docstore), req.state, req.discom, date.today()
    )
    pdf = _build(result, checklist_doc, body.lang, engine_version(), consent)
    key = f"{PDF_PREFIX}{secrets.token_urlsafe(16)}_{body.lang.value}.pdf"
    state.adapters.blobstore.put(key, pdf, content_type="application/pdf")
    return ok(
        {
            "url": f"/documents/file/{key}",
            "expires_at": date.today().isoformat() + "+24h",
            "language": body.lang.value,
        },
        request,
        policy_version=result["policy_version"],
    )


@router.get("/documents/file/{key:path}")
def download(key: str, state: StateDep) -> Response:
    from packages.agent.tools import PDF_PREFIX

    if not key.startswith(PDF_PREFIX) or ".." in key:
        raise NotFoundError("document not found")
    return Response(
        state.adapters.blobstore.get(key),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="suryacheck-summary.pdf"'},
    )
