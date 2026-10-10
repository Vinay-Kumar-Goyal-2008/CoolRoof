"""M11+12+13 Cool-roof impact, cost and people protected.

No coefficient is asserted: every quantity is a low/base/high range built from
P-* parameters, and any quantity whose parameters are null ([NV]) is
``unavailable`` with the missing parameter IDs listed.

    f_b        = eligible_roof_area_b / pixel_area
    ΔT_pix,b   = P-KCOOL · P-DALB · f_b
    ΔT_indoor  = P-KIND · P-DALB · 1[top floor]
    Cost_b     = roof_area_b · P-CM2 · (1 + P-PREP)
    Protected_b = pop_b · φ_b,  φ_b = 1/floors_est if known, else P-PHI
    BC_b       = Protected_b · heat_weight_b / Cost_b

``heat_weight_b`` is the building's neighbourhood ΔLST clipped at 0 (°C): a
building in a cooler-than-rural neighbourhood gets no heat benefit weight.
Without ``P-CM2`` the benefit is still reported but the BC ratio is refused.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import pandas as pd

from packages.core.errors import ParameterUnavailableError
from packages.core.params import ParamRegistry, ScenarioTriple

__all__ = ["BudgetPlan", "Range", "RoofAssessment", "assess_roofs", "plan_budget"]


@dataclass(frozen=True)
class Range:
    low: float
    base: float
    high: float

    @classmethod
    def point(cls, v: float) -> Range:
        return cls(v, v, v)

    def scale(self, k: float) -> Range:
        lo, hi = sorted((self.low * k, self.high * k))
        return Range(lo, self.base * k, hi)

    def as_dict(self, digits: int = 2) -> dict[str, float]:
        return {
            "low": round(self.low, digits),
            "base": round(self.base, digits),
            "high": round(self.high, digits),
        }

    def __add__(self, other: Range) -> Range:
        return Range(self.low + other.low, self.base + other.base, self.high + other.high)


ZERO = Range(0.0, 0.0, 0.0)
_COOLROOF_PARAMS = ("P-CM2", "P-DALB", "P-KCOOL", "P-KIND", "P-PREP")


@dataclass
class RoofAssessment:
    building_id: str
    ward_id: str
    eligible: bool
    area_m2: float
    roof_fraction_of_pixel: float
    heat_weight_c: float | None
    protected: Range
    cost_inr: Range | None
    bc: Range | None  # people·°C per ₹
    dt_neighbourhood_c: Range | None
    dt_indoor_c: Range | None
    unavailable: dict[str, list[str]] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()

    @property
    def benefit(self) -> Range:
        """Protected people weighted by neighbourhood heat (°C·people)."""
        return self.protected.scale(self.heat_weight_c or 0.0)

    def to_dict(self) -> dict[str, object]:
        def r(x: Range | None, digits: int = 2) -> dict[str, float] | None:
            return x.as_dict(digits) if x else None

        return {
            "protected_people": r(self.protected, 1),
            "cost_inr": r(self.cost_inr, 0),
            "benefit": r(self.benefit, 2),
            "bc_people_c_per_lakh_inr": r(self.bc.scale(100_000) if self.bc else None, 3),
            "dt_neighbourhood_c": r(self.dt_neighbourhood_c, 3),
            "dt_indoor_c": r(self.dt_indoor_c, 3),
            "heat_weight_c": self.heat_weight_c,
            "unavailable": self.unavailable,
            "assumptions": list(self.assumptions),
        }


def _triple(params: ParamRegistry, pid: str) -> ScenarioTriple | None:
    return params.optional_triple(pid)


def _scalar_or_triple(params: ParamRegistry, pid: str) -> Range | None:
    value = params.get(pid)
    if value is None:
        return None
    if isinstance(value, dict):
        t = ScenarioTriple.model_validate(value)
        return Range(t.low, t.base, t.high)
    return Range.point(float(value))


def assess_roofs(
    roofs: pd.DataFrame, pixel_area_m2: float, params: ParamRegistry
) -> list[RoofAssessment]:
    """Assess every roof. ``roofs`` columns: building_id, ward_id, area_m2, pop_b,
    heat_local_c, floors (nullable), eligible."""
    phi = _triple(params, "P-PHI")
    prep = _triple(params, "P-PREP")
    cm2 = _scalar_or_triple(params, "P-CM2")
    dalb = _scalar_or_triple(params, "P-DALB")
    kcool = _scalar_or_triple(params, "P-KCOOL")
    kind = _scalar_or_triple(params, "P-KIND")
    if phi is None or prep is None:
        raise ParameterUnavailableError("P-PHI" if phi is None else "P-PREP")

    out: list[RoofAssessment] = []
    for row in roofs.itertuples(index=False):
        area = float(row.area_m2)
        f_b = area / pixel_area_m2
        floors = row.floors if row.floors is not None and not pd.isna(row.floors) else None
        if floors:
            phi_range = Range.point(1.0 / float(floors))
            phi_note = "phi=1/floors_est"
        else:
            phi_range = Range(phi.low, phi.base, phi.high)
            phi_note = "P-PHI"
        pop = float(row.pop_b)
        protected = Range(pop * phi_range.low, pop * phi_range.base, pop * phi_range.high)
        heat = float(row.heat_local_c) if math.isfinite(float(row.heat_local_c)) else None
        heat_weight = max(heat, 0.0) if heat is not None else None

        missing: dict[str, list[str]] = {}
        cost = None
        if cm2 is not None:
            cost = Range(
                area * cm2.low * (1 + prep.low),
                area * cm2.base * (1 + prep.base),
                area * cm2.high * (1 + prep.high),
            )
        else:
            missing["cost_inr"] = ["P-CM2"]
        bc = None
        if cost is not None and heat_weight is not None and cost.low > 0:
            bc = Range(
                protected.low * heat_weight / cost.high,
                protected.base * heat_weight / cost.base,
                protected.high * heat_weight / cost.low,
            )
        elif cost is None:
            missing["bc"] = ["P-CM2"]

        dt_pix = None
        if kcool is not None and dalb is not None:
            dt_pix = Range(
                kcool.low * dalb.low * f_b,
                kcool.base * dalb.base * f_b,
                kcool.high * dalb.high * f_b,
            )
        else:
            missing["dt_neighbourhood_c"] = [
                p for p, v in (("P-KCOOL", kcool), ("P-DALB", dalb)) if v is None
            ]
        dt_in = None
        if kind is not None and dalb is not None:
            dt_in = Range(kind.low * dalb.low, kind.base * dalb.base, kind.high * dalb.high)
        else:
            missing["dt_indoor_c"] = [
                p for p, v in (("P-KIND", kind), ("P-DALB", dalb)) if v is None
            ]

        out.append(
            RoofAssessment(
                building_id=str(row.building_id),
                ward_id=str(row.ward_id),
                eligible=bool(row.eligible),
                area_m2=area,
                roof_fraction_of_pixel=f_b,
                heat_weight_c=heat_weight,
                protected=protected,
                cost_inr=cost,
                bc=bc,
                dt_neighbourhood_c=dt_pix,
                dt_indoor_c=dt_in,
                unavailable=missing,
                assumptions=_COOLROOF_PARAMS + (("P-PHI",) if phi_note == "P-PHI" else ()),
            )
        )
    return out


@dataclass
class BudgetPlan:
    budget_inr: float
    selected: list[RoofAssessment]
    total_cost: Range
    total_protected: Range

    @property
    def n_roofs(self) -> int:
        return len(self.selected)


def plan_budget(roofs: Iterable[RoofAssessment], budget_inr: float) -> BudgetPlan:
    """Greedy knapsack by base BC ratio; the base-scenario cost never exceeds the budget.

    Raises ``ParameterUnavailableError('P-CM2')`` when costs are unavailable.
    """
    candidates: Sequence[RoofAssessment] = [r for r in roofs if r.eligible]
    if any(r.cost_inr is None or r.bc is None for r in candidates):
        raise ParameterUnavailableError("P-CM2")
    ordered = sorted(candidates, key=lambda r: (-r.bc.base, r.building_id))  # type: ignore[union-attr]
    chosen: list[RoofAssessment] = []
    total_cost, total_protected, spent = ZERO, ZERO, 0.0
    for roof in ordered:
        cost = roof.cost_inr
        assert cost is not None
        if spent + cost.base <= budget_inr:
            chosen.append(roof)
            spent += cost.base
            total_cost = total_cost + cost
            total_protected = total_protected + roof.protected
    return BudgetPlan(budget_inr, chosen, total_cost, total_protected)
