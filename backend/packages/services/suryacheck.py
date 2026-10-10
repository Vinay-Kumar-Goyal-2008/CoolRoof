"""SuryaCheck (M25–M32): rooftop-solar assessment for a household or RWA.

Chain: solar resource (M25) → roof suitability (M26) → size and generation
(M27+28) → PM Surya Ghar subsidy (M29) → net metering and payback (M30+31).
Each step returns ok / partial / unavailable and a failed step never aborts a
later one that can still run. Pure function of its inputs (``input_hash``).

Every number is a :class:`Field` with a class (FACT / ASSUMPTION / USER /
ESTIMATE) and pre-formatted en/hi display strings, so the UI, agent and PDF show
identical text. The subsidy is computed from the policy record's tiers — no
rupee figure lives in this file.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from packages.core.enums import (
    Eligibility,
    FieldClass,
    Language,
    PaybackStatus,
    StepStatus,
    Suitability,
    SuryaCheckStatus,
)
from packages.core.errors import (
    PolicyUnavailableError,
    UpstreamError,
)
from packages.core.i18n import format_inr
from packages.core.ids import input_hash
from packages.core.params import ParamRegistry
from packages.services.policy_store import PolicyRecord, PolicyStore, PolicyType

__all__ = [
    "SolarInputs",
    "SolarResource",
    "SolarSource",
    "SuryaCheckRequest",
    "SuryaCheckResult",
    "compute_subsidy",
    "run_suryacheck",
    "simulate_payback",
]

Applicant = Literal["residential", "ghs_rwa"]
MONTHS = 12


# ============================================================================ models
class DisplayField(BaseModel):
    """One displayed number with class and bilingual display strings."""

    value: float | str | None
    cls: FieldClass = Field(alias="class")
    unit: str | None = None
    en: str
    hi: str
    assumptions: list[str] = Field(default_factory=list)
    note: str | None = None

    model_config = {"populate_by_name": True}


def _fld(
    value: float | None,
    cls: FieldClass,
    unit: str,
    en: str,
    hi: str | None = None,
    assumptions: list[str] | None = None,
    note: str | None = None,
) -> DisplayField:
    return DisplayField(
        value=value,
        cls=cls,
        unit=unit,
        en=en,
        hi=hi or en,
        assumptions=assumptions or [],
        note=note,
    )


class SuryaCheckRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    state: str
    discom: str
    roof_area_m2: float | None = Field(default=None, gt=0)
    free_area_m2: float | None = Field(default=None, gt=0)
    monthly_kwh: list[float] | None = None  # 12 values, user's own bill data
    avg_monthly_kwh: float | None = Field(default=None, gt=0)
    gross_cost_inr: float | None = Field(default=None, gt=0)
    applicant: Applicant = "residential"
    shaded: bool = False
    shared_roof: bool = False
    owns_roof: bool | None = None
    require_policy: bool = False
    on_date: date | None = None


@dataclass(frozen=True)
class SolarResource:
    specific_yield: dict[str, float]  # low/base/high kWh/kWp/yr
    monthly_base: list[float]  # kWh/kWp, loss-free baseline
    source: str
    stale: bool = False


class SolarSource:
    """PVGIS → NASA POWER+pvlib → cache → unavailable; fixture mode offline."""

    def __init__(self, fixture_path: Path | None, live: bool = False) -> None:
        self._fixture = fixture_path
        self._live = live
        self._cache: dict[str, SolarResource] = {}

    @staticmethod
    def cell(lat: float, lon: float) -> str:
        return f"{round(lat, 1)},{round(lon, 1)}"

    def fetch(self, lat: float, lon: float, tilt: float, az: float) -> SolarResource | None:
        cell = self.cell(lat, lon)
        key = f"{cell}|{round(tilt)}|{round(az)}"
        if self._live:
            try:
                res = self._pvgis(lat, lon, tilt, az)
                self._cache[key] = res
                return res
            except (httpx.HTTPError, KeyError, ValueError):
                cached = self._cache.get(key)
                return (
                    SolarResource(
                        cached.specific_yield, cached.monthly_base, cached.source, stale=True
                    )
                    if cached
                    else None
                )
        if self._fixture and self._fixture.exists():
            data = json.loads(self._fixture.read_text(encoding="utf-8"))
            if cell in data:
                monthly = [m["E_m"] for m in data[cell]["outputs"]["monthly"]["fixed"]]
                return SolarResource({}, monthly, f"fixture_pvgis:{cell}")
        return None

    @staticmethod
    def _pvgis(lat: float, lon: float, tilt: float, az: float) -> SolarResource:
        # PVGIS aspect: 0 = south; compass azimuth 180 = south → aspect = az - 180 [R: verify]
        r = httpx.get(
            "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc",
            timeout=15.0,
            params={
                "lat": lat,
                "lon": lon,
                "peakpower": 1,
                "loss": 0,
                "angle": tilt,
                "aspect": az - 180,
                "outputformat": "json",
            },
        )
        r.raise_for_status()
        out = r.json()["outputs"]
        monthly = [m["E_m"] for m in out["monthly"]["fixed"]]
        return SolarResource({}, monthly, "pvgis_v5_2")


@dataclass
class SolarInputs:
    params: ParamRegistry
    policies: PolicyStore
    solar: SolarSource


class SuryaCheckResult(BaseModel):
    status: SuryaCheckStatus
    input_hash: str
    steps: dict[str, StepStatus]
    missing: list[str]
    next_questions: list[str]
    solar: dict[str, Any] | None = None
    roof: dict[str, Any] | None = None
    system: dict[str, Any] | None = None
    subsidy: dict[str, Any] | None = None
    payback: dict[str, Any] | None = None
    policy_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    disclaimer_en: str = (
        "Assistance summary — not the official application. "
        "Apply at pmsuryaghar.gov.in; final eligibility is decided there."
    )
    disclaimer_hi: str = (
        "सहायता सारांश — आधिकारिक आवेदन नहीं। pmsuryaghar.gov.in पर आवेदन करें; "
        "अंतिम पात्रता वहीं तय होती है।"
    )


# ============================================================================ M29
def compute_subsidy(kw: float, tiers: list[dict[str, float]], max_eligible_kw: float) -> float:
    """Generic tiered subsidy: Σ rate_i · kW falling in tier i, with kW capped at ``max_eligible_kw``."""
    capped = min(kw, max_eligible_kw)
    total = 0.0
    for tier in tiers:
        lo, hi, rate = tier["from_kw"], tier["to_kw"], tier["inr_per_kw"]
        total += rate * max(0.0, min(capped, hi) - lo)
    return total


def _subsidy_for(policy: PolicyRecord, applicant: Applicant, kw: float) -> float:
    doc = policy.doc
    if applicant == "ghs_rwa":
        g = doc["ghs_rwa"]
        return float(g["inr_per_kw"]) * min(kw, float(g["max_kw"]))
    r = doc["residential"]
    return compute_subsidy(kw, r["tiers"], float(r["max_eligible_kw"]))


# ============================================================================ M30+31
def _bill(consumption: float, slabs: list[dict[str, Any]], fixed: float) -> float:
    remaining, cost = max(consumption, 0.0), fixed
    for slab in slabs:
        lo, hi, rate = slab["from_kwh"], slab.get("to_kwh"), slab["inr_per_kwh"]
        width = (hi - lo) if hi is not None else math.inf
        used = min(remaining, width)
        cost += used * rate
        remaining -= used
        if remaining <= 0:
            break
    return cost


def simulate_payback(
    monthly_consumption: list[float],
    gen_year1: list[float],
    tariff: dict[str, Any],
    settlement: dict[str, Any],
    net_cost: float,
    params: ParamRegistry,
    om_inr: float,
    inverter_inr: float,
    self_use: float,
) -> dict[str, float | None]:
    """Monthly simulation over the horizon for one generation scenario."""
    horizon = int(params.require("P-HORIZON"))
    esc = params.require_float("P-ESC")
    deg = params.require_float("P-DEG")
    inv_year = int(params.require("P-INV")["year"])
    slabs, fixed = tariff["slabs"], float(tariff.get("fixed_charge_inr_per_month", 0))
    mode = settlement["mode"]
    export_rate = float(settlement.get("export_rate_inr_per_kwh", 0.0))
    cum, payback_cum, savings_1 = -net_cost, None, 0.0
    bank = 0.0
    for year in range(1, horizon + 1):
        factor = (1 - deg) ** (year - 1)
        saved = 0.0
        credit = 0.0
        for m in range(MONTHS):
            c, g = monthly_consumption[m], gen_year1[m] * factor
            without = _bill(c, slabs, fixed)
            if mode == "net_metering":
                net = c - g - bank
                billed_kwh = max(net, 0.0)
                bank = max(-net, 0.0)
                with_ = _bill(billed_kwh, slabs, fixed)
            else:  # net_billing
                self_c = min(g * self_use, c)
                with_ = _bill(c - self_c, slabs, fixed)
                credit += (g - self_c) * export_rate
            saved += without - with_
        saved = (saved + credit) * (1 + esc) ** (year - 1)
        if year == 1:
            savings_1 = saved
        outflow = om_inr + (inverter_inr if year == inv_year else 0.0)
        previous = cum
        cum += saved - outflow
        if payback_cum is None and cum >= 0:
            step = saved - outflow
            payback_cum = (year - 1) + (-previous / step if step > 0 else 1.0)
    simple = net_cost / savings_1 if savings_1 > 0 else None
    return {"savings_year1": savings_1, "payback_simple": simple, "payback_cum": payback_cum}


# ============================================================================ orchestrator
def _bilingual_inr(value: float) -> tuple[str, str]:
    return format_inr(value, lang=Language.EN), format_inr(value, lang=Language.HI)


def run_suryacheck(req: SuryaCheckRequest, ctx: SolarInputs) -> SuryaCheckResult:
    p = ctx.params
    on = req.on_date or date.today()
    steps: dict[str, StepStatus] = {}
    missing: list[str] = []
    questions: list[str] = []
    warnings: list[str] = []
    h = input_hash(req.model_dump(mode="json"))

    # ------------------------------------------------ M25 solar resource
    tilt = abs(round(req.lat)) if p.get("P-TILT") == "latitude" else float(p.require("P-TILT"))
    az = float(p.require("P-AZ"))
    resource = ctx.solar.fetch(req.lat, req.lon, tilt, az)
    solar_out: dict[str, Any] | None = None
    yields: dict[str, float] | None = None
    if resource is None:
        steps["solar"] = StepStatus.UNAVAILABLE
        missing.append("solar_resource")
    else:
        loss = p.require_triple("P-LOSS")
        annual0 = sum(resource.monthly_base)
        # low-yield scenario uses the highest loss
        yields = {
            "low": annual0 * (1 - loss.high),
            "base": annual0 * (1 - loss.base),
            "high": annual0 * (1 - loss.low),
        }
        steps["solar"] = StepStatus.PARTIAL if resource.stale else StepStatus.OK
        if resource.stale:
            warnings.append("solar data is from a cached cell and may be out of date")
        solar_out = {
            "specific_yield_kwh_per_kwp": {k: round(v) for k, v in yields.items()},
            "monthly_loss_free_kwh_per_kwp": [round(m, 1) for m in resource.monthly_base],
            "source": resource.source,
            "tilt_deg": tilt,
            "azimuth_deg": az,
            "assumptions": ["P-LOSS", "P-TILT", "P-AZ"],
        }
        band = p.require("P-SOLAR-BAND")
        if not band["min_kwh_per_kwp"] <= yields["base"] <= band["max_kwh_per_kwp"]:
            warnings.append("solar yield is outside the plausible band for India — verify")

    # ------------------------------------------------ M26 roof suitability
    roof_out: dict[str, Any] | None = None
    usable: dict[str, float] | None = None
    if req.free_area_m2:
        usable = {"low": req.free_area_m2, "base": req.free_area_m2, "high": req.free_area_m2}
        area_class = FieldClass.USER
    elif req.roof_area_m2:
        u = p.require_triple("P-U")
        usable = {
            "low": req.roof_area_m2 * u.low,
            "base": req.roof_area_m2 * u.base,
            "high": req.roof_area_m2 * u.high,
        }
        area_class = FieldClass.ASSUMPTION
    else:
        area_class = FieldClass.ESTIMATE
        steps["roof"] = StepStatus.UNAVAILABLE
        missing.append("roof_area")
        questions += ["roof_area_or_free_area"]
    if usable:
        akw, kwmin = p.require_float("P-AKW"), p.require_float("P-KWMIN")
        kw_area_base = usable["base"] / akw
        if kw_area_base < kwmin:
            suit = Suitability.UNSUITABLE
        elif req.shaded:
            suit = Suitability.CHECK_OBSTRUCTIONS
        else:
            suit = Suitability.SUITABLE
        if req.shared_roof:
            questions.append("shared_roof_use_rwa_path")
        steps["roof"] = StepStatus.OK
        roof_out = {
            "suitability": suit.value,
            "usable_area_m2": {k: round(v, 1) for k, v in usable.items()},
            "area_class": area_class.value,
            "assumptions": [] if area_class is FieldClass.USER else ["P-U"],
        }
        if req.roof_area_m2 and req.free_area_m2:
            ratio = req.free_area_m2 / req.roof_area_m2
            if ratio > 1:
                warnings.append("free area exceeds roof area — please re-check the outline")

    # ------------------------------------------------ M27+28 size and generation
    system_out: dict[str, Any] | None = None
    kw_rec: float | None = None
    consumption: list[float] | None = None
    if req.monthly_kwh and len(req.monthly_kwh) == MONTHS:
        consumption = list(req.monthly_kwh)
    elif req.avg_monthly_kwh:
        consumption = [req.avg_monthly_kwh] * MONTHS
    if usable and yields:
        akw, step_kw = p.require_float("P-AKW"), p.require_float("P-KWSTEP")
        deg, lid = p.require_float("P-DEG"), p.require_float("P-LID")
        kw_area = usable["base"] / akw
        limits = {"area": kw_area}
        if consumption:
            limits["load"] = sum(consumption) / yields["base"]
        limiting = min(limits, key=limits.__getitem__)
        kw_max = limits[limiting]
        kw_rec = math.floor(kw_max / step_kw + 1e-9) * step_kw
        if kw_rec <= 0:
            kw_rec = 0.0
        gen = {s: kw_rec * y * (1 - lid) for s, y in yields.items()}
        base_monthly = (
            [
                kw_rec * (m / sum(resource.monthly_base)) * yields["base"] * (1 - lid)
                for m in resource.monthly_base
            ]
            if resource
            else []
        )
        steps["system"] = StepStatus.OK if consumption else StepStatus.PARTIAL
        if not consumption:
            missing.append("consumption")
            questions.append("monthly_bill_units")
        system_out = {
            "kw_recommended": kw_rec,
            "kw_max_continuous": round(kw_max, 2),
            "limiting_factor": limiting if consumption else "area_upper_bound",
            "generation_year1_kwh": {k: round(v) for k, v in gen.items()},
            "generation_year_n_factor": f"(1-{deg})^(t-1)",
            "monthly_generation_kwh": [round(m, 1) for m in base_monthly],
            "slab_guidance_f2": "0–150 units: 1–2 kW · 150–300: 2–3 kW · >300: >3 kW",
            "assumptions": ["P-AKW", "P-KWSTEP", "P-DEG", "P-LID"],
        }
    else:
        steps["system"] = StepStatus.UNAVAILABLE

    # ------------------------------------------------ M29 subsidy
    subsidy_out: dict[str, Any] | None = None
    policy, level = ctx.policies.resolve(PolicyType.SUBSIDY, state="ALL", discom="ALL", on=on)
    subsidy_inr: float | None = None
    policy_version: str | None = None
    if policy is None:
        steps["subsidy"] = StepStatus.UNAVAILABLE
        missing.append("subsidy_policy")
        if req.require_policy:
            raise PolicyUnavailableError("subsidy policy record is missing")
    else:
        policy_version = policy.version
        age = policy.age_days(on)
        hard = p.require_float("P-HARD-POLICY")
        soft = p.require_float("P-STALE-POLICY")
        if age is not None and age > hard and req.require_policy:
            raise PolicyUnavailableError("subsidy policy record is too old to produce a PDF")
        if age is not None and age > soft:
            warnings.append(f"subsidy policy was last reviewed {age} days ago")
        if kw_rec is not None:
            subsidy_inr = _subsidy_for(policy, req.applicant, kw_rec)
            en, hi = _bilingual_inr(subsidy_inr)
            steps["subsidy"] = StepStatus.OK
            subsidy_out = {
                "amount": _fld(subsidy_inr, FieldClass.FACT, "INR", en, hi).model_dump(
                    by_alias=True
                ),
                "applicant": req.applicant,
                "state_topup": "unknown",
                "eligibility": Eligibility.UNCONFIRMED.value,
                "estimate": kw_rec != int(kw_rec),
                "policy_version": policy.version,
                "effective_date": policy.effective_date,
                "source_url": policy.doc.get("source_url"),
                "rule_id": policy.doc.get("rule_id"),
                "record_hash": policy.hash,
                "resolved_at_level": level,
                "note": "State top-up is unknown, not zero. Final eligibility is decided on the national portal.",
            }
        else:
            steps["subsidy"] = StepStatus.UNAVAILABLE

    # ------------------------------------------------ M30+31 payback
    payback_out: dict[str, Any] = {"status": PaybackStatus.UNAVAILABLE_NO_TARIFF.value}
    tariff, _ = ctx.policies.resolve(PolicyType.TARIFF, state=req.state, discom=req.discom, on=on)
    settlement, _ = ctx.policies.resolve(
        PolicyType.NETMETERING, state=req.state, discom=req.discom, on=on
    )
    status: PaybackStatus
    if tariff is None or settlement is None:
        status = PaybackStatus.UNAVAILABLE_NO_TARIFF
    elif (tariff.age_days(on) or 0) > p.require_float("P-HARD-POLICY"):
        status = PaybackStatus.UNAVAILABLE_STALE_TARIFF
    elif consumption is None:
        status = PaybackStatus.UNAVAILABLE_NO_CONSUMPTION
    elif req.gross_cost_inr is None:
        status = (
            PaybackStatus.RANGE_COST_ASSUMED
        )  # no gross-cost parameter exists ([NV]) → ask user
    else:
        status = PaybackStatus.OK
    payback_out["status"] = status.value
    if (
        status is PaybackStatus.OK
        and kw_rec
        and resource
        and subsidy_inr is not None
        and tariff
        and settlement
        and yields
    ):
        net_cost = req.gross_cost_inr - subsidy_inr  # type: ignore[operator]
        om = p.require_float("P-OM") * req.gross_cost_inr  # type: ignore[operator]
        inv = float(p.require("P-INV")["cost_fraction"]) * req.gross_cost_inr  # type: ignore[operator]
        self_use = p.require_float("P-SELF")
        assert consumption is not None  # status OK implies consumption was given
        results = {}
        for scen in ("low", "base", "high"):
            monthly_gen = [
                kw_rec * (m / sum(resource.monthly_base)) * yields[scen]
                for m in resource.monthly_base
            ]
            results[scen] = simulate_payback(
                consumption, monthly_gen, tariff.doc, settlement.doc, net_cost, p, om, inv, self_use
            )
        simple = {s: r["payback_simple"] for s, r in results.items()}
        cum = {s: r["payback_cum"] for s, r in results.items()}
        payback_out.update(
            {
                "net_cost_inr": round(net_cost),
                "savings_year1_inr": {
                    s: round(r["savings_year1"] or 0) for s, r in results.items()
                },
                "payback_simple_years": {s: round(v, 1) if v else None for s, v in simple.items()},
                "payback_cumulative_years": {s: round(v, 1) if v else None for s, v in cum.items()},
                "tariff_synthetic": tariff.is_synthetic,
                "assumptions": ["P-ESC", "P-DEG", "P-OM", "P-INV", "P-SELF", "P-HORIZON"],
            }
        )
        steps["payback"] = StepStatus.OK
        if tariff.is_synthetic:
            warnings.append("tariff is SYNTHETIC test data — not a real DISCOM tariff")
    else:
        steps["payback"] = StepStatus.UNAVAILABLE
        missing.append(status.value)
        if status in (PaybackStatus.UNAVAILABLE_NO_CONSUMPTION,):
            questions.append("monthly_bill_units")
        if req.gross_cost_inr is None:
            questions.append("gross_cost_quote")

    complete = all(s is StepStatus.OK for s in steps.values()) and len(steps) == 5
    if resource is None and system_out is None and roof_out is None:
        raise UpstreamError("solar resource unavailable and nothing else could be computed")
    return SuryaCheckResult(
        status=SuryaCheckStatus.COMPLETE if complete else SuryaCheckStatus.PARTIAL,
        input_hash=h,
        steps=steps,
        missing=sorted(set(missing)),
        next_questions=sorted(set(questions)),
        solar=solar_out,
        roof=roof_out,
        system=system_out,
        subsidy=subsidy_out,
        payback=payback_out,
        policy_version=policy_version,
        warnings=warnings,
    )
