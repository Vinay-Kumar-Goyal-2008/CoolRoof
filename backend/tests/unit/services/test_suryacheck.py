"""SuryaCheck Verify bullets: subsidy table, payback fixture, statuses, golden JSON."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from packages.adapters.docstore import SQLiteDocStore
from packages.core.errors import PolicyUnavailableError
from packages.core.params import ParamRegistry
from packages.services.policy_store import PolicyStore
from packages.services.suryacheck import (
    SolarInputs,
    SolarSource,
    SuryaCheckRequest,
    compute_subsidy,
    run_suryacheck,
    simulate_payback,
)
from scripts.seed import seed_policies

BACKEND = Path(__file__).resolve().parents[3]
FIXTURE = BACKEND / "tests" / "fixtures" / "mini_city" / "solar_pvgis.json"
ON = date(2026, 10, 10)
TIERS = [
    {"from_kw": 0, "to_kw": 2, "inr_per_kw": 30000},
    {"from_kw": 2, "to_kw": 3, "inr_per_kw": 18000},
]


@pytest.fixture
def ctx(tmp_path: Path, params: ParamRegistry) -> SolarInputs:
    store = PolicyStore(SQLiteDocStore(tmp_path / "p.db"))
    seed_policies(store, BACKEND / "seed")
    return SolarInputs(params, store, SolarSource(FIXTURE))


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        (0.5, 15000),
        (1, 30000),
        (2, 60000),
        (2.5, 69000),
        (3, 78000),
        (3.5, 78000),
        (10, 78000),
    ],
)
def test_subsidy_table(kw: float, expected: float) -> None:
    assert compute_subsidy(kw, TIERS, 3) == expected


def _req(**kw: object) -> SuryaCheckRequest:
    base = dict(lat=18.52, lon=73.86, state="TEST", discom="TEST-DISCOM", on_date=ON)
    return SuryaCheckRequest(**{**base, **kw})  # type: ignore[arg-type]


def test_payback_arithmetic_fixture_is_two_years(params: ParamRegistry) -> None:
    flat = params.with_overrides(
        {"P-ESC": 0.0, "P-DEG": 0.0, "P-OM": 0.0, "P-INV": {"year": 12, "cost_fraction": 0.0}}
    )
    tariff = {
        "slabs": [{"from_kwh": 0, "to_kwh": None, "inr_per_kwh": 8.0}],
        "fixed_charge_inr_per_month": 0,
    }
    result = simulate_payback(
        [500.0] * 12,
        [375.0] * 12,
        tariff,
        {"mode": "net_metering"},
        72000.0,
        flat,
        om_inr=0.0,
        inverter_inr=0.0,
        self_use=0.5,
    )
    assert result["savings_year1"] == pytest.approx(36000)
    assert result["payback_simple"] == pytest.approx(2.0)
    assert result["payback_cum"] == pytest.approx(2.0)


def test_three_kw_gets_78000_with_provenance(ctx: SolarInputs) -> None:
    res = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400), ctx)
    assert res.system["kw_recommended"] == 3  # type: ignore[index]
    sub = res.subsidy
    assert sub is not None and sub["amount"]["value"] == 78000
    assert sub["amount"]["en"] == "₹78,000" and sub["amount"]["class"] == "FACT"
    assert sub["policy_version"] == "subsidy:ALL:ALL:2024-02-29" and sub["record_hash"]
    assert sub["state_topup"] == "unknown" and sub["eligibility"] == "unconfirmed"


def test_full_run_with_user_inputs_has_payback_range(ctx: SolarInputs) -> None:
    res = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400, gross_cost_inr=180000), ctx)
    assert res.status.value == "complete"
    pb = res.payback
    assert pb is not None and pb["status"] == "ok"
    assert pb["payback_simple_years"]["low"] >= pb["payback_simple_years"]["high"]
    assert any("SYNTHETIC" in w for w in res.warnings)


def test_missing_consumption_gives_area_upper_bound_and_question(ctx: SolarInputs) -> None:
    res = run_suryacheck(_req(roof_area_m2=70), ctx)
    assert res.status.value == "partial"
    assert res.system["limiting_factor"] == "area_upper_bound"  # type: ignore[index]
    assert "monthly_bill_units" in res.next_questions
    assert res.payback["status"] == "payback_unavailable_no_consumption"  # type: ignore[index]


def test_unsupported_discom_has_no_payback_but_keeps_subsidy(ctx: SolarInputs) -> None:
    res = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400, discom="OTHER"), ctx)
    assert res.payback["status"] == "payback_unavailable_no_tariff"  # type: ignore[index]
    assert res.subsidy is not None


def test_no_cost_means_cost_assumed_status_not_a_headline(ctx: SolarInputs) -> None:
    res = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400), ctx)
    assert res.payback["status"] == "payback_range_cost_assumed"  # type: ignore[index]
    assert "payback_simple_years" not in res.payback  # type: ignore[operator]


def test_stale_policy_blocks_pdf_but_not_assessment(ctx: SolarInputs) -> None:
    late = date(2027, 6, 1)
    ok = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400, on_date=late), ctx)
    assert any("reviewed" in w for w in ok.warnings)
    with pytest.raises(PolicyUnavailableError):
        run_suryacheck(
            _req(roof_area_m2=70, avg_monthly_kwh=400, on_date=late, require_policy=True), ctx
        )


def test_more_area_never_reduces_kw(ctx: SolarInputs) -> None:
    prev = -1.0
    for area in (10, 20, 40, 80, 160):
        kw = run_suryacheck(_req(roof_area_m2=area), ctx).system["kw_recommended"]  # type: ignore[index]
        assert kw >= prev
        prev = kw


def test_idempotent_and_golden_json(ctx: SolarInputs) -> None:
    a = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400, gross_cost_inr=180000), ctx)
    b = run_suryacheck(_req(roof_area_m2=70, avg_monthly_kwh=400, gross_cost_inr=180000), ctx)
    assert a.model_dump() == b.model_dump()
    golden = Path(__file__).resolve().parents[2] / "golden" / "suryacheck" / "pune_residential.json"
    snapshot = json.loads(a.model_dump_json())
    if not golden.exists():
        golden.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    assert snapshot == json.loads(golden.read_text(encoding="utf-8"))
