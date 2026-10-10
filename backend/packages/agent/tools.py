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
from packages.adapters.docstore import DocStore
from packages.core.context import WardContext
from packages.core.enums import Language
from packages.core.errors import CoolRoofError
from packages.core.ids import record_hash
from packages.core.params import ParamRegistry
from packages.services.m17_reco import load_rules, matched_cooling, recommend
from packages.services.m20_readiness import readiness
from packages.services.m35_pdf import build_pdf, select_checklist
from packages.services.m37_alerts import AlertHub
from packages.services.policy_store import PolicyStore, PolicyType
from packages.services.repository import Repository
from packages.services.signals import current_signals
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
    docs: DocStore | None = None
    hub: AlertHub | None = None

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

    def _contexts(self) -> list[WardContext]:
        return [WardContext.model_validate(d["ward_context"]) for d in self.repo.wards(self.city)]

    def get_roof_context(self, ward_id: str, building_id: str) -> dict[str, Any]:
        doc = self.repo.roof(ward_id, building_id)
        rc, a = doc["roof_context"], doc["assessment"]
        return {
            "building_id": building_id,
            "ward_id": ward_id,
            "area_m2": rc["area"]["value"],
            "local_heat_c": rc["local_heat"].get("value"),
            "eligible": rc["eligible"],
            "benefit_rank": doc["benefit_rank"],
            "assessment": a,
            "caveat": "Individual roofs cannot be resolved from Landsat; this is a neighbourhood estimate.",
        }

    def get_drivers(self, ward_id: str) -> dict[str, Any]:
        doc = self.repo.drivers(self.city, ward_id)
        if doc["status"] != "ok":
            return {"ward_id": ward_id, "status": doc["status"], "top": []}
        effect = {
            "warmer": {"en": "warmer", "hi": "अधिक गर्म"},
            "cooler": {"en": "cooler", "hi": "अधिक ठंडा"},
        }
        top = sorted(doc["drivers"], key=lambda d: -abs(d["contribution_c"]))[:3]
        return {
            "ward_id": ward_id,
            "status": "ok",
            "top": [
                {
                    "label": d["label"],
                    "contribution_c": d["contribution_c"],
                    "magnitude_c": abs(d["contribution_c"]),  # text states the direction in words
                    "effect": effect[d["direction"]],
                    "stable": d["stable"],
                }
                for d in top
            ],
            "unobserved": doc["unobserved"],
            "wording": "associated with, not proven causes",
        }

    def get_cooling_options(self, ward_id: str, lang: str = "en") -> dict[str, Any]:
        doc = self.repo.ward(self.city, ward_id)
        ctx = WardContext.model_validate(doc["ward_context"])
        rules = load_rules(self.rules_dir, self.rules_version)
        return matched_cooling(ctx, doc["heat_type"]["type"], rules, self.params, lang)

    def get_readiness(self, ward_id: str, lang: str = "en") -> dict[str, Any]:
        docs = self.repo.wards(self.city)
        mine = next(d for d in docs if d["ward_context"]["ward_id"] == ward_id)
        forecast = self.repo.manifest(self.city).get("forecast")
        signals = current_signals(self._docs(), self.city, forecast)
        return readiness(
            ward_id,
            self._contexts(),
            mine["heat_type"]["type"],
            signals,
            self.params,
            lang,
        )

    def get_degradation(self, ward_id: str) -> dict[str, Any]:
        doc = self.repo.soil(self.city, ward_id)
        t = doc["trends"]
        slope = (t.get("ndvi") or {}).get("slope_per_year")
        rising = slope is not None and slope > 0
        return {
            "ndvi_slope_abs": None if slope is None else abs(slope),
            "ndvi_direction": {
                "en": "rising" if rising else "falling",
                "hi": "बढ़ती" if rising else "घटती",
            },
            "ward_id": ward_id,
            "signal": doc["degradation_signal"],
            "ndvi_slope_per_year": (t.get("ndvi") or {}).get("slope_per_year"),
            "n_years": (t.get("ndvi") or {}).get("n_years"),
            "label": doc["label"],
            "caveats": doc["caveats"],
        }

    def get_habitat_pressure(self) -> dict[str, Any]:
        areas = self.repo.protected_areas(self.city)
        return {
            "areas": [
                {"name": a["name"], "hpi": a["hpi"], "pressure": a["pressure"]} for a in areas
            ],
            "disclaimer": "habitat pressure indicator, unverified — not a measured biodiversity loss",
        }

    def _docs(self) -> DocStore:
        if self.docs is None:
            raise CoolRoofError("document store is not wired for this tool")
        return self.docs

    def get_alerts(self, ward_id: str | None = None, lang: str = "en") -> dict[str, Any]:
        """Public alerts only (staff-only items are never shown to the assistant)."""
        if self.hub is None:
            return {"alerts": []}
        rows = self.hub.active(self.city, ward_id, include_staff=False)
        return {
            "alerts": [
                {
                    "type": a["type"],
                    "severity": a["severity"],
                    "text": a["texts"].get(lang) or a["texts"]["en"],
                    "valid_until": a["valid_until"][:10],
                }
                for a in rows
            ]
        }

    def get_advisory(self, ward_id: str | None = None, lang: str = "en") -> dict[str, Any]:
        """Latest published, unexpired *public* advisory (approved by a planner)."""
        from packages.services.m18_advisory import AdvisoryService

        docs = self._docs()
        from packages.adapters.docstore import Table

        rows = docs.query(Table.ADVISORIES, f"city#{self.city}", descending=True, limit=50)
        for a in rows:
            if (
                a["status"] == "published"
                and a["audience"] == "public"
                and AdvisoryService.deliverable(a)
                and a["ward_id"] in (None, ward_id)
            ):
                return {
                    "advisory_id": a["advisory_id"],
                    "text": a["texts"].get(lang) or a["texts"]["en"],
                    "valid_until": a["valid_until"][:10],
                }
        return {"advisory_id": None, "text": None}

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
            "get_roof_context",
            "get_drivers",
            "get_cooling_options",
            "get_readiness",
            "get_degradation",
            "get_habitat_pressure",
            "get_alerts",
            "get_advisory",
        }
    )
