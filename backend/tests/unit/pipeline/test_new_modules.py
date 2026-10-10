"""Unit tests for M16, M20, M22–M24, M43 extensions and the tile builder."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from packages.core.enums import DegradationSignal, FireConfidence, HabitatPressure
from packages.core.params import ParamRegistry, load_params
from packages.pipeline.m16_drivers import morans_i, vif_filter
from packages.pipeline.m22_fire import normalise_confidence
from packages.pipeline.m23_habitat import _classify, _hpi
from packages.pipeline.m24_degradation import compute_trends, signal_from_adverse, trend_test
from packages.pipeline.m38_tiles import colorize
from packages.pipeline.m43_heatdome import forecast_heatdome, imd_style_check
from packages.pipeline.runner import PipelineRun


@pytest.fixture(scope="module")
def params() -> ParamRegistry:
    return load_params()


# ------------------------------------------------------------------------------- M24
def _series(
    unit: str, ndvi: list[float], bsi: list[float], lst: list[float], valid: float = 0.9
) -> pd.DataFrame:
    n = len(ndvi)
    return pd.DataFrame(
        {
            "unit_id": unit,
            "unit_kind": "ward",
            "year": list(range(2014, 2014 + n)),
            "ndvi": ndvi,
            "bsi": bsi,
            "lst_c": lst,
            "valid_frac": valid,
            "rain_mm": 650.0,
        }
    )


def test_trend_classes_for_up_down_flat_noisy(params: ParamRegistry) -> None:
    rng = np.random.default_rng(1)
    years = np.arange(12)
    up = trend_test(0.3 + 0.01 * years, "bsi", 0.05, 8)
    down = trend_test(0.5 - 0.01 * years, "ndvi", 0.05, 8)
    flat = trend_test(np.full(12, 0.4), "ndvi", 0.05, 8)
    noisy = trend_test(0.4 + 0.2 * rng.standard_normal(12), "ndvi", 0.05, 8)
    short = trend_test(np.arange(5.0), "ndvi", 0.05, 8)
    assert up.trend.value == "increasing" and up.adverse
    assert down.trend.value == "declining" and down.adverse
    assert flat.trend.value == "stable" and not flat.adverse
    assert not noisy.significant
    assert short.trend.value == "insufficient_data"


def test_signal_counts_adverse_trends(params: ParamRegistry) -> None:
    assert [signal_from_adverse(n).value for n in range(4)] == [
        "none",
        "weak",
        "moderate",
        "strong",
    ]
    yrs = np.arange(12)
    df = _series("A", list(0.5 - 0.01 * yrs), list(0.1 + 0.01 * yrs), list(40 + 0.1 * yrs))
    out = compute_trends(df, {"A": 0.2}, params)["A"]
    assert out.signal is DegradationSignal.STRONG and out.stability_share == 1.0
    assert (
        out.to_dict()["status"] == "indicator"
        and out.to_dict()["label"] == "indicator, not diagnosis"
    )


def test_built_wards_are_not_applicable_and_short_series_insufficient(
    params: ParamRegistry,
) -> None:
    yrs = np.arange(12)
    df = _series("B", list(0.5 - 0.01 * yrs), [0.1] * 12, [40.0] * 12)
    assert compute_trends(df, {"B": 0.95}, params)["B"].signal is DegradationSignal.NOT_APPLICABLE
    short = _series("C", [0.5, 0.4, 0.3], [0.1] * 3, [40.0] * 3)
    assert (
        compute_trends(short, {"C": 0.1}, params)["C"].signal is DegradationSignal.INSUFFICIENT_DATA
    )


def test_years_below_coverage_are_dropped(params: ParamRegistry) -> None:
    yrs = np.arange(9)
    df = _series("D", list(0.5 - 0.02 * yrs), [0.1] * 9, [40.0] * 9)
    df.loc[df.year.isin([2014, 2015]), "valid_frac"] = 0.1  # 7 valid years < P-TREND-MIN (8)
    assert compute_trends(df, {"D": 0.1}, params)["D"].signal is DegradationSignal.INSUFFICIENT_DATA


# ------------------------------------------------------------------------------- M23
def test_hpi_is_monotonic_in_each_indicator(params: ParamRegistry) -> None:
    base = {"I_veg": {"pct": 0.2}, "I_heat": {"pct": 0.2}, "I_loss": {"pct": 0.2}}
    for key in base:
        higher = {**base, key: {"pct": 0.9}}
        assert _hpi(higher, params) > _hpi(base, params)  # type: ignore[operator]


def test_hpi_needs_two_indicators_and_classes_follow_thresholds(params: ParamRegistry) -> None:
    assert _hpi({"I_veg": {"pct": 0.9}}, params) is None
    assert _classify(None, 1, params) is HabitatPressure.INSUFFICIENT_DATA
    assert [_classify(v, 3, params).value for v in (0.1, 0.5, 0.9)] == ["low", "moderate", "high"]


def test_fixture_habitat_edge_point_counts_inside(mini_run: PipelineRun) -> None:
    ev = [e for e in mini_run.fire_events if e.protected_area_id == "PA-MINI-1"]
    assert ev  # inside and edge detections attach to the area
    for pa in mini_run.habitat:
        assert pa.disclaimer.startswith("habitat pressure indicator")


# ------------------------------------------------------------------------------- M22
def test_confidence_normalisation_keeps_both_forms() -> None:
    assert normalise_confidence("h", "VIIRS") is FireConfidence.HIGH
    assert normalise_confidence("n", "VIIRS") is FireConfidence.NOMINAL
    assert normalise_confidence("l", "VIIRS") is FireConfidence.LOW
    assert [normalise_confidence(v, "MODIS").value for v in (10, 50, 95)] == [
        "low",
        "nominal",
        "high",
    ]
    assert normalise_confidence("garbage", "MODIS") is FireConfidence.LOW


def test_fire_classes_and_alert_rule_on_fixture(mini_run: PipelineRun) -> None:
    classes = [e.fire_class.value for e in mini_run.fire_events]
    assert classes.count("forest_fire") == 1 and classes.count("persistent_source") == 6
    alerts = [e for e in mini_run.fire_events if e.alert]
    assert alerts and all(e.fire_class.value in {"forest_fire", "vegetation_fire"} for e in alerts)
    assert all(e.confidence is FireConfidence.HIGH for e in alerts)
    assert all(e.severity in {"low", "medium", "high"} for e in alerts)


# ------------------------------------------------------------------------------- M20
def test_facility_counts_match_the_planted_layout(mini_run: PipelineRun) -> None:
    f = mini_run.facilities
    assert f is not None
    assert f["hospital_count"].sum() == 6 and f["school_count"].sum() == 12
    assert f.loc[["W04", "W10", "W12"], "cooling_point_count"].eq(1).all()
    assert f["nearest_hospital_m"].notna().all()
    assert (f["facilities_per_10k_exposed"].dropna() >= 0).all()


# ------------------------------------------------------------------------------- M16
def test_vif_filter_drops_one_of_a_collinear_pair() -> None:
    rng = np.random.default_rng(0)
    a = rng.standard_normal(500)
    frame = pd.DataFrame(
        {"ndvi": a, "ndbi": -a + 0.01 * rng.standard_normal(500), "x": rng.standard_normal(500)}
    )
    keep, dropped = vif_filter(frame, 5.0)
    assert dropped == ["ndbi"] and "ndvi" in keep and "x" in keep  # the vegetation index is kept


def test_morans_i_detects_spatial_structure() -> None:
    rng = np.random.default_rng(0)
    xy = rng.uniform(0, 1000, (400, 2))
    smooth = np.sin(xy[:, 0] / 150)
    assert morans_i(xy, smooth) > 0.5
    assert abs(morans_i(xy, rng.standard_normal(400))) < 0.15


def test_drivers_on_fixture_have_ci_and_unobserved(mini_run: PipelineRun) -> None:
    res = mini_run.drivers
    assert res is not None and res.model_card["unobserved"]
    ok = [w for w in res.wards.values() if w.status == "ok"]
    assert ok
    for d in ok[0].drivers:
        assert d["ci_low"] <= d["contribution_c"] <= d["ci_high"]
    assert len(ok[0].top) <= 3


# ------------------------------------------------------------------------------- M43
def _nwp(z: bool) -> dict:  # type: ignore[type-arg]
    days = 6
    members = [
        {"member": i, "tmax_c": [46.0] * days, "z500_box_mean_m": [5900.0] * days if z else None}
        for i in range(10)
    ]
    clim = [
        {
            "date": f"2026-05-{d + 1:02d}",
            "tmax_mean_c": 38.0,
            "tmax_p90_c": 41.0,
            "z500_mean_m": 5860.0 if z else None,
            "z500_std_m": 20.0 if z else None,
        }
        for d in range(days)
    ]
    return {
        "members": members,
        "climatology": clim,
        "dates": [c["date"] for c in clim],
        "source": "t",
    }


def test_temperature_only_forecast_is_capped_at_watch(params: ParamRegistry) -> None:
    full = forecast_heatdome(_nwp(True), params)
    capped = forecast_heatdome(_nwp(False), params)
    assert full.risk.value == "high" and full.criteria_mode == "temperature_and_ridge"
    assert (
        capped.risk.value == "watch"
        and capped.low_confidence
        and capped.criteria_mode == "temperature_only"
    )


def test_missing_forecast_is_unavailable_never_old_data(params: ParamRegistry) -> None:
    assert forecast_heatdome(None, params).risk.value == "unavailable"


def test_imd_style_label_is_never_an_imd_warning() -> None:
    crit = {
        "criteria": {
            "min_tmax_c": {"plains": 40.0},
            "departure_c": {"heatwave": 4.5},
            "absolute_tmax_c": {"heatwave": 45.0},
        }
    }
    res = imd_style_check(np.array([[46.0, 41.0]]), np.array([38.0, 38.0]), crit)
    assert res and res["meets"] and res["not_an_imd_warning"] and "IMD-style" in res["label"]
    assert imd_style_check(np.array([[39.0]]), np.array([38.0]), crit)["meets"] is False  # type: ignore[index]
    assert imd_style_check(np.array([[46.0]]), np.array([38.0]), None) is None


# ------------------------------------------------------------------------------- tiles
def test_colorize_transparent_for_nan_and_ordered_ramp() -> None:
    arr = np.array([[np.nan, -5.0, 0.0, 5.0]])
    rgba = colorize(arr, -5.0, 5.0)
    assert rgba[0, 0, 3] == 0 and rgba[0, 1, 3] > 0
    assert rgba[0, 3, 0] > rgba[0, 1, 0]  # hotter = redder
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    assert buf.getvalue()[:4] == b"\x89PNG"


# ------------------------------------------------------------------------------- M43 evaluation
def test_forecast_scores_and_sensitivity_on_the_planted_fixture(params: ParamRegistry) -> None:
    import json

    from packages.pipeline.m43_eval import score_forecasts, sensitivity

    pairs = [(0.9, True), (0.8, True), (0.5, False), (0.1, False), (0.2, True), (0.0, False)]
    s = score_forecasts(pairs)
    assert s["hit_rate"] == pytest.approx(2 / 3) and s["false_alarm_ratio"] == pytest.approx(1 / 3)
    assert 0 < s["brier"] < 0.25
    assert score_forecasts([])["n"] == 0
    nwp = json.loads(
        (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "fixtures"
            / "mini_city"
            / "nwp_ensemble.json"
        ).read_text(encoding="utf-8")
    )
    rows = sensitivity(nwp, params, {"P-HD-T": [1.0, 3.0, 12.0], "P-HD-DAYS": [2, 3, 6]})
    by = {(r["param"], r["value"]): r["p_event"] for r in rows}
    assert (
        by[("P-HD-T", 12.0)] == 0.0 and by[("P-HD-T", 3.0)] == 0.75
    )  # planted event needs the threshold to be sane
    assert by[("P-HD-DAYS", 6)] == 0.0 and by[("P-HD-DAYS", 2)] >= by[("P-HD-DAYS", 3)]
