"""Agent tools (M33+34): typed, deterministic, JSON out. The agent never computes numbers.

Admin and planner write tools are never registered here. Each call's output is stored in the
session so replies can be rendered from, and grounded against, tool results only.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from packages.adapters.blobstore import BlobStore
from packages.core.context import WardContext
from packages.core.enums import Language
from packages.core.errors import CoolRoofError
from packages.core.ids import record_hash
from packages.core.params import ParamRegistry
from packages.services.m17_reco import load_rules, recommend
from packages.services.m35_pdf import build_pdf, select_checklist
from packages.services.policy_store import PolicyStore, PolicyType
from packages.services.repository import Repository
from packages.services.suryacheck import (
    SolarInputs,
    SolarSource,
    SuryaCheckRequest,
    run_suryacheck,
)

__all__ = ["PDF_PREFIX", "AgentTools"]

PDF_PREFIX = "exports/pdf/"
PDF_TTL_HOURS = 24


@dataclass
class AgentTools:
    repo: Repository
    policies: PolicyStore
    solar: SolarSource
    params: ParamRegistry
    blobs: BlobStore
    rules_dir: Any
    rules_version: str
    engine_version: str
    city: str

    # ------------------------------------------------------------------ MVP tools
    def get_ward_context(self, ward_id: str) -> dict[str, Any]:
        """Ward context summary: heat, population, priority rank (all with provenance)."""
        doc = self.repo.ward(self.city, ward_id)
        ctx = doc["ward_context"]
        return {
            "ward_id": ward_id,
            "name": ctx["location"]["name"],
            "name_hi": ctx["location"]["name_hi"],
            "rank": doc["priority"]["rank"],
            "priority": doc["priority"]["priority"],
            "rank_interval": doc["priority"]["rank_interval"],
            "mean_dlst_c": ctx["heat"].get("mean_dlst_c"),
            "population": ctx["population"].get("population"),
            "exposed_population": ctx["population"].get("exposed_population"),
            "data_quality": ctx["data_quality"],
            "caveat": "LST is the surface temperature at a late-morning satellite pass, not air temperature.",
        }

    def get_solar_assessment(self, **kwargs: Any) -> dict[str, Any]:
        """Run SuryaCheck. kwargs follow ``SuryaCheckRequest``."""
        req = SuryaCheckRequest(**kwargs)
        result = run_suryacheck(req, SolarInputs(self.params, self.policies, self.solar))
        return result.model_dump(mode="json", by_alias=True)

    def get_subsidy_rules(self, state: str = "ALL", discom: str = "ALL") -> dict[str, Any]:
        record, _level = self.policies.resolve(PolicyType.SUBSIDY, state="ALL", discom="ALL")
        if record is None:
            return {"status": "unavailable", "reason": "subsidy policy record missing"}
        d = record.doc
        return {
            "policy_version": record.version,
            "record_hash": record.hash,
            "effective_date": record.effective_date,
            "source_url": d.get("source_url"),
            "residential_tiers": d["residential"]["tiers"],
            "max_eligible_kw": d["residential"]["max_eligible_kw"],
            "ghs_rwa_inr_per_kw": d["ghs_rwa"]["inr_per_kw"],
            "portal": d["applications_portal"],
            "eligibility": "unconfirmed",
            "state_topup": "unknown",
        }

    def get_checklist(self, state: str, discom: str) -> dict[str, Any]:
        checklist = select_checklist(self.policies, state, discom, date.today())
        return {
            "level": checklist["level"],
            "version": checklist["version"],
            "items": [
                {"id": i["id"], "title": i["title_i18n"], "detail": i["detail_i18n"]}
                for i in checklist["items"]
            ],
            "banner": checklist["banner"],
        }

    def generate_application_pdf(
        self,
        assessment: dict[str, Any],
        state: str,
        discom: str,
        lang: str,
        consent: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """PDF summary. Blocks (424) when the subsidy policy is stale — via ``require_policy``."""
        req = {**assessment.get("_request", {}), "require_policy": True}
        fresh = self.get_solar_assessment(**req) if req.get("lat") is not None else assessment
        checklist = select_checklist(self.policies, state, discom, date.today())
        pdf = build_pdf(fresh, checklist, Language(lang), self.engine_version, consent)
        key = f"{PDF_PREFIX}{secrets.token_urlsafe(16)}_{lang}.pdf"
        self.blobs.put(key, pdf, content_type="application/pdf")
        return {
            "url": f"/documents/file/{key}",
            "key": key,
            "language": lang,
            "expires_at": (date.today() + timedelta(days=1)).isoformat(),
            "hash": record_hash({"key": key}),
        }

    @staticmethod
    def request_user_input(fields: list[str]) -> dict[str, Any]:
        return {"needs": fields}

    # ------------------------------------------------------------------ heat tools
    def get_heat_analysis(self, ward_id: str) -> dict[str, Any]:
        doc = self.repo.ward(self.city, ward_id)
        rules = load_rules(self.rules_dir, self.rules_version)
        htype = doc["heat_type"]
        return {
            "ward_id": ward_id,
            "heat_type": htype["type"],
            "confidence": htype["confidence"],
            "brief": rules.briefs.get(htype["type"], {}),
        }

    def get_recommendations(self, ward_id: str, lang: str = "en") -> dict[str, Any]:
        docs = self.repo.wards(self.city)
        contexts = [WardContext.model_validate(d["ward_context"]) for d in docs]
        mine = next(d for d in docs if d["ward_context"]["ward_id"] == ward_id)
        rules = load_rules(self.rules_dir, self.rules_version)
        return recommend(
            ward_id,
            contexts,
            mine["priority"]["priority_pct"],
            mine["heat_type"]["type"],
            rules,
            self.params,
            lang,
        )

    def get_heatdome_forecast(self) -> dict[str, Any]:
        forecast = self.repo.manifest(self.city).get("forecast")
        return forecast or {"risk": "unavailable"}

    # ------------------------------------------------------------------ dispatch
    def call(self, name: str, **kwargs: Any) -> dict[str, Any]:
        if name not in self.REGISTRY:
            raise ValueError(f"unknown tool {name!r}")
        try:
            return getattr(self, name)(**kwargs)  # type: ignore[no-any-return]
        except CoolRoofError as exc:
            return {"error": exc.status_code, "message": exc.message}

    REGISTRY = frozenset(
        {
            "get_ward_context",
            "get_solar_assessment",
            "get_subsidy_rules",
            "get_checklist",
            "generate_application_pdf",
            "request_user_input",
            "get_heat_analysis",
            "get_recommendations",
            "get_heatdome_forecast",
        }
    )
