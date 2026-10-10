"""M24 Land / soil degradation tracking (indicator, not diagnosis).

Per ward (and protected area) hot-season yearly medians of NDVI, BSI and LST are tested with
Mann–Kendall (Hamed–Rao correction for serial correlation) and Sen's slope. Years with valid
coverage below ``P-COVMIN`` are treated as missing. NDVI is rainfall-adjusted when rainfall is
available (the residual trend is tested); raw and adjusted results are both reported.

Land Degradation Signal = number of adverse significant trends among {NDVI ↓, BSI ↑, LST ↑}:
0 none · 1 weak · 2 moderate · 3 strong. Fully built wards are ``not_applicable``; fewer than
``P-TREND-MIN`` valid years is ``insufficient_data``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pymannkendall as mk

from packages.core.enums import DegradationSignal, TrendClass
from packages.core.params import ParamRegistry

__all__ = ["TrendResult", "UnitTrends", "compute_trends", "signal_from_adverse", "trend_test"]

INDICATORS = ("ndvi", "bsi", "lst_c")
ADVERSE_DIRECTION = {"ndvi": -1, "bsi": +1, "lst_c": +1}  # sign of an adverse slope
LABEL = "indicator, not diagnosis"


@dataclass(frozen=True)
class TrendResult:
    slope_per_year: float | None
    p_value: float | None
    trend: TrendClass
    significant: bool
    adverse: bool
    n_years: int


@dataclass
class UnitTrends:
    unit_id: str
    unit_kind: str
    signal: DegradationSignal
    trends: dict[str, TrendResult] = field(default_factory=dict)
    ndvi_rain_adjusted: TrendResult | None = None
    stability_share: float | None = None  # share of leave-one-year-out runs with the same signal
    series: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def tr(t: TrendResult | None) -> dict[str, Any] | None:
            if t is None:
                return None
            return {
                "slope_per_year": t.slope_per_year,
                "p_value": t.p_value,
                "trend": t.trend.value,
                "significant": t.significant,
                "adverse": t.adverse,
                "n_years": t.n_years,
            }

        return {
            "unit_id": self.unit_id,
            "unit_kind": self.unit_kind,
            "degradation_signal": self.signal.value,
            "trends": {k: tr(v) for k, v in self.trends.items()},
            "ndvi_rain_adjusted": tr(self.ndvi_rain_adjusted),
            "stability_share": self.stability_share,
            "series": self.series,
            "caveats": self.caveats,
            "status": "indicator",
            "label": LABEL,
        }


def signal_from_adverse(count: int) -> DegradationSignal:
    return (
        DegradationSignal.NONE,
        DegradationSignal.WEAK,
        DegradationSignal.MODERATE,
        DegradationSignal.STRONG,
    )[min(max(count, 0), 3)]


def _serially_correlated(values: np.ndarray, slope: float, intercept: float) -> bool:
    """Lag-1 autocorrelation of the detrended series exceeds its ~95 % noise band."""
    resid = values - (slope * np.arange(len(values)) + intercept)
    if np.ptp(resid) < 1e-12:
        return False
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])
    return bool(np.isfinite(r1) and abs(r1) > 1.96 / np.sqrt(len(values)))


def trend_test(values: np.ndarray, indicator: str, alpha: float, min_years: int) -> TrendResult:
    """Mann–Kendall + Sen's slope on a yearly series (NaN years already removed)."""
    n = len(values)
    if n < min_years:
        return TrendResult(None, None, TrendClass.INSUFFICIENT_DATA, False, False, n)
    if np.ptp(values) == 0:  # constant series: no trend, variance of S is zero
        return TrendResult(0.0, 1.0, TrendClass.STABLE, False, False, n)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        res = mk.original_test(values)
        if n >= 10 and _serially_correlated(values, float(res.slope), float(res.intercept)):
            res = mk.hamed_rao_modification_test(
                values
            )  # correct only when residuals are correlated
    if not np.isfinite(res.p):
        return TrendResult(round(float(res.slope), 5), None, TrendClass.STABLE, False, False, n)
    significant = bool(res.p < alpha)
    slope = float(res.slope)
    trend = (
        TrendClass.STABLE
        if not significant
        else TrendClass.INCREASING
        if slope > 0
        else TrendClass.DECLINING
    )
    adverse = significant and np.sign(slope) == ADVERSE_DIRECTION[indicator]
    return TrendResult(
        round(slope, 5), round(float(res.p), 5), trend, significant, bool(adverse), n
    )


def _unit_signal(
    frame: pd.DataFrame, params: ParamRegistry
) -> tuple[DegradationSignal, dict[str, TrendResult], TrendResult | None, list[str]]:
    alpha = params.require_float("P-TREND-ALPHA")
    min_years = int(params.require_float("P-TREND-MIN"))
    covmin = params.require_float("P-COVMIN")
    valid = frame[frame["valid_frac"] >= covmin].sort_values("year")
    caveats: list[str] = []
    if len(valid) < min_years:
        return DegradationSignal.INSUFFICIENT_DATA, {}, None, caveats
    trends = {
        ind: trend_test(valid[ind].to_numpy(dtype=float), ind, alpha, min_years)
        for ind in INDICATORS
    }
    adjusted: TrendResult | None = None
    if (
        "rain_mm" in valid
        and valid["rain_mm"].notna().all()
        and valid["rain_mm"].nunique() > 1
        and len(valid) >= min_years
    ):
        rain = valid["rain_mm"].to_numpy(dtype=float)
        ndvi = valid["ndvi"].to_numpy(dtype=float)
        slope, intercept = np.polyfit(rain, ndvi, 1)
        residual = ndvi - (slope * rain + intercept)
        adjusted = trend_test(residual, "ndvi", alpha, min_years)
        ndvi_adverse = adjusted.adverse
    else:
        ndvi_adverse = trends["ndvi"].adverse
        caveats.append("vegetation also responds to rainfall")
    count = int(ndvi_adverse) + int(trends["bsi"].adverse) + int(trends["lst_c"].adverse)
    return signal_from_adverse(count), trends, adjusted, caveats


def compute_trends(
    series: pd.DataFrame | None,
    built_fraction: dict[str, float],
    params: ParamRegistry,
) -> dict[str, UnitTrends]:
    """Trend results for every unit (ward or protected area) in ``series``."""
    if series is None or series.empty:
        return {}
    built_na = params.require_float("P-BUILT-NA")
    out: dict[str, UnitTrends] = {}
    for unit_id, frame in series.groupby("unit_id"):
        uid = str(unit_id)
        kind = str(frame["unit_kind"].iloc[0])
        records = frame.sort_values("year")[["year", "ndvi", "bsi", "lst_c", "valid_frac"]].to_dict(
            "records"
        )
        if kind == "ward" and built_fraction.get(uid, 0.0) > built_na:
            out[uid] = UnitTrends(uid, kind, DegradationSignal.NOT_APPLICABLE, series=records)
            continue
        signal, trends, adjusted, caveats = _unit_signal(frame, params)
        stability = None
        if signal is not DegradationSignal.INSUFFICIENT_DATA:
            same = []
            for year in frame["year"].unique():
                sub_signal, *_ = _unit_signal(frame[frame["year"] != year], params)
                same.append(sub_signal is signal)
            stability = round(float(np.mean(same)), 3)
        out[uid] = UnitTrends(uid, kind, signal, trends, adjusted, stability, records, caveats)
    return out


def context_table(trends: dict[str, UnitTrends]) -> pd.DataFrame:
    """Ward-level feature table for M8.5 (slopes per year, signal)."""
    rows = {}
    for uid, t in trends.items():
        if t.unit_kind != "ward":
            continue
        rows[uid] = {
            "ndvi_trend_slope": t.trends["ndvi"].slope_per_year if "ndvi" in t.trends else None,
            "bsi_trend_slope": t.trends["bsi"].slope_per_year if "bsi" in t.trends else None,
            "lst_trend_slope": t.trends["lst_c"].slope_per_year if "lst_c" in t.trends else None,
            "degradation_signal": t.signal.value,
        }
    return pd.DataFrame.from_dict(rows, orient="index")
