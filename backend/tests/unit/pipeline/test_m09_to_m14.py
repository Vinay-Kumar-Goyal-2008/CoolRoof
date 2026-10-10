"""Verify bullets for M9 (priority), M10 (roofs), M11–13 (cool-roof ranges) and M14 (actions)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from scipy import stats

from packages.core.context import DataQuality, LocationSection, WardContext
from packages.core.enums import UnitType, ValueClass
from packages.core.envelope import ValueEnvelope
from packages.core.errors import ParameterUnavailableError
from packages.core.params import ParamRegistry
from packages.pipeline.m09_priority import score_wards
from packages.pipeline.m10_roofs import rank_roofs
from packages.pipeline.m11_coolroof import assess_roofs, plan_budget
from packages.pipeline.m14_actions import CSV_COLUMNS, build_action_plan
from packages.pipeline.runner import PipelineRun


def _ctx(
    ward: str,
    dlst: float | None,
    pers: float,
    exposed: float | None,
    ndvi: float,
    eligible_m2: float,
) -> WardContext:
    def env(v: float | None) -> ValueEnvelope:
        if v is None:
            return ValueEnvelope.unavailable("toy", "missing")
        return ValueEnvelope.of(v, ValueClass.DERIVED, "toy")

    return WardContext(
        ward_id=ward,
        boundary_version="toy",
        context_version="v",
        run_id="r",
        location=LocationSection(
            city="toy",
            state="T",
            centroid=(0, 0),
            area_km2=1.0,
            unit_type=UnitType.WARD,
            name=ward,
            name_hi=ward,
        ),
        heat={"mean_dlst_c": env(dlst), "persistence": env(pers)},
        population={"exposed_population": env(exposed)},
        environment={"ndvi_mean": env(ndvi)},
        built_environment={"eligible_roof_area_m2": env(eligible_m2)},
        data_quality=DataQuality(context_confidence=1.0),
    )


# ------------------------------------------------------------------ M9
def test_hand_computed_toy_city(params: ParamRegistry) -> None:
    """Three wards, z-score CDF normalisation (fewer than P-SMALL-CITY wards)."""
    contexts = [
        _ctx("A", 4.0, 0.6, 1000, 0.10, 400_000),
        _ctx("B", 2.0, 0.3, 500, 0.30, 200_000),
        _ctx("C", 0.0, 0.0, 0.0, 0.50, 0.0),
    ]
    result = score_wards(contexts, params)
    by = result.by_ward()
    assert result.normalisation == "zscore_cdf"
    # Every component of B is exactly the city mean → Φ(0) = 0.5 → Need 0.5, R 0.5.
    assert by["B"].need == pytest.approx(0.5, abs=1e-4)
    assert by["B"].priority == pytest.approx(0.5 * (0.5 + 0.5 * 0.5), abs=1e-4)
    # A is +1.2247σ on every axis → Φ = 0.8897
    assert by["A"].need == pytest.approx(0.8897, abs=1e-3)
    assert [s.ward_id for s in result.scores] == ["A", "B", "C"]


def test_missing_variable_is_dropped_and_recorded(params: ParamRegistry) -> None:
    contexts = [
        _ctx("A", 4.0, 0.6, None, 0.10, 4e5),
        _ctx("B", 2.0, 0.3, 500, 0.30, 2e5),
        _ctx("C", None, 0.0, None, 0.50, 0.0),
    ]
    by = score_wards(contexts, params).by_ward()
    assert "E" not in by["A"].variables_used
    assert by["A"].score_confidence < by["B"].score_confidence
    assert by["C"].priority is None and by["C"].unscored_reason


def test_mini_city_ranking_and_sensitivity(mini_run: PipelineRun) -> None:
    result = mini_run.require(mini_run.priority, "M9")
    ranks = {s.ward_id: s.rank for s in result.scores}
    assert ranks["W07"] < ranks["W10"]  # dense hot ward above green campus
    assert {ranks[w] for w in ("W04", "W05", "W10")} == {10, 11, 12}  # green wards last
    for s in result.scores:
        assert s.rank_interval is not None
        lo, hi = s.rank_interval
        assert lo <= s.rank <= hi or abs(lo - s.rank) <= 1  # type: ignore[operator]
    assert set(result.sensitivity["leave_one_out_spearman"]) == {"H", "P", "E", "V", "R"}  # type: ignore[arg-type]
    assert result.sensitivity["additive_spearman"] > 0.8  # type: ignore[operator]


# ------------------------------------------------------------------ M10–13
def test_without_coating_cost_benefit_only_and_bc_refused(mini_run: PipelineRun) -> None:
    roofs = mini_run.roof_assessments
    assert roofs
    assert all(r.cost_inr is None and r.bc is None for r in roofs)
    assert all(r.unavailable["cost_inr"] == ["P-CM2"] for r in roofs)
    ranking = rank_roofs(roofs, "W07", buildings_incomplete=False)
    assert ranking.basis == "benefit_only"
    with pytest.raises(ParameterUnavailableError):
        plan_budget(roofs, 1_00_00_000)


def test_ranking_withheld_for_incomplete_ward(mini_run: PipelineRun) -> None:
    ranking = rank_roofs(mini_run.roof_assessments, "W09", buildings_incomplete=True)
    assert ranking.roofs == [] and ranking.withheld_reason


def _costed(mini_run: PipelineRun, cm2: float) -> list:  # type: ignore[type-arg]
    params = mini_run.params.with_overrides({"P-CM2": cm2})
    b = mini_run.require(mini_run.buildings, "M7").buildings
    pop = mini_run.require(mini_run.population, "M8")
    frame = pd.DataFrame(
        {
            "building_id": b.building_id,
            "ward_id": b.ward_id,
            "area_m2": b.area_m2,
            "pop_b": pop.building_pop.reindex(b.building_id).to_numpy(),
            "heat_local_c": pop.building_heat_local.reindex(b.building_id).to_numpy(dtype=float),
            "floors": b.floors,
            "eligible": b.eligible & ~b.ward_id.isin(mini_run.incomplete_wards),
        }
    )
    return assess_roofs(frame, 900.0, params)


def test_cost_is_linear_in_area_and_rate(mini_run: PipelineRun) -> None:
    a, b = _costed(mini_run, 200.0), _costed(mini_run, 400.0)
    for ra, rb in zip(a[:20], b[:20], strict=True):
        assert rb.cost_inr.base == pytest.approx(2 * ra.cost_inr.base)
        assert ra.cost_inr.base / ra.area_m2 == pytest.approx(a[0].cost_inr.base / a[0].area_m2)


def test_phi_bounds(mini_run: PipelineRun) -> None:
    for roof in _costed(mini_run, 200.0):
        assert 0 <= roof.protected.low <= roof.protected.base <= roof.protected.high


def test_roof_ranks_stable_under_20_percent_cost_change(mini_run: PipelineRun) -> None:
    def order(cm2: float) -> list[str]:
        rk = rank_roofs(_costed(mini_run, cm2), "W07", buildings_incomplete=False)
        return [r.roof.building_id for r in rk.roofs]

    base, lo, hi = order(250.0), order(200.0), order(300.0)
    assert stats.spearmanr(range(len(base)), [lo.index(x) for x in base]).statistic > 0.99
    assert stats.spearmanr(range(len(base)), [hi.index(x) for x in base]).statistic > 0.99


# ------------------------------------------------------------------ M14
def test_action_plan_within_budget_and_reproducible(mini_run: PipelineRun) -> None:
    roofs = _costed(mini_run, 250.0)
    scores = mini_run.require(mini_run.priority, "M9").scores
    budget = 20_00_000.0
    plan = build_action_plan(scores, roofs, budget, incomplete_wards=mini_run.incomplete_wards)
    assert plan.rows
    assert plan.total_cost.base <= budget
    assert "W09" not in {r.ward_id for r in plan.rows}
    again = build_action_plan(
        scores, _costed(mini_run, 250.0), budget, incomplete_wards=mini_run.incomplete_wards
    )
    assert plan.csv_hash == again.csv_hash
    header = plan.to_csv().splitlines()[0].split(",")
    assert tuple(header) == CSV_COLUMNS


def test_action_plan_needs_costs(mini_run: PipelineRun) -> None:
    with pytest.raises(ParameterUnavailableError):
        build_action_plan(
            mini_run.require(mini_run.priority, "M9").scores,
            mini_run.roof_assessments,
            1e6,
            incomplete_wards=set(),
        )


def test_run_date_is_used_for_context_version(mini_run: PipelineRun) -> None:
    assert mini_run.context_version == date(2026, 10, 10).isoformat()
