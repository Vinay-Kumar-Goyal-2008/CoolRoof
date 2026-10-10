"""M23 Habitat Pressure Index (HPI) per protected area — an indicator, never a species count.

Indicators (each yearly, vs the area's own history when only one area exists):
* I_fire  – vegetation-fire events inside + buffer (FIRMS, M22) vs the area's own mean
* I_loss  – tree/vegetation loss proxy: NDVI drop > ``P-VEG-DROP`` vs the previous mean
            (Hansen tree-cover loss is the preferred source and is not wired here)
* I_veg   – NDVI Sen's slope with Mann–Kendall significance (M24 series)
* I_heat  – LST Sen's slope (M24 series)

``HPI = Σ w_i · pct_i`` over the available indicators (weights renormalised); fewer than two
indicators → ``insufficient_data``. Messages carry "habitat pressure indicator, unverified — not a
measured biodiversity loss".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pymannkendall as mk

from packages.core.enums import FireClass, HabitatPressure
from packages.core.params import ParamRegistry
from packages.pipeline.m22_fire import FireEvent

__all__ = ["DISCLAIMER", "PAPressure", "compute_habitat_pressure", "ward_pressure_table"]

DISCLAIMER = "habitat pressure indicator, unverified — not a measured biodiversity loss"
# Fixed scales that map a trend to 0..1 when there are too few areas to rank against each other
# (single-area fallback "against its own history", see docs/GAPS.md).
_VEG_SLOPE_SCALE = 0.02  # NDVI per year
_LST_SLOPE_SCALE = 0.20  # °C per year
_RANK = {
    HabitatPressure.INSUFFICIENT_DATA: -1,
    HabitatPressure.LOW: 0,
    HabitatPressure.MODERATE: 1,
    HabitatPressure.HIGH: 2,
}


@dataclass
class PAPressure:
    pa_id: str
    name: str
    hpi: float | None
    pressure: HabitatPressure
    indicators: dict[str, dict[str, Any]] = field(default_factory=dict)
    previous_pressure: HabitatPressure | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "pa_id": self.pa_id,
            "name": self.name,
            "hpi": self.hpi,
            "pressure": self.pressure.value,
            "previous_pressure": self.previous_pressure.value if self.previous_pressure else None,
            "indicators": self.indicators,
            "warnings": self.warnings,
            "disclaimer": self.disclaimer,
            "status": "indicator",
        }


def _classify(hpi: float | None, n_ind: int, params: ParamRegistry) -> HabitatPressure:
    if hpi is None or n_ind < 2:
        return HabitatPressure.INSUFFICIENT_DATA
    theta = params.require("P-HPI-THETA")
    return (
        HabitatPressure.HIGH
        if hpi >= theta["high"]
        else HabitatPressure.MODERATE
        if hpi >= theta["moderate"]
        else HabitatPressure.LOW
    )


def _indicators_upto(
    frame: pd.DataFrame, params: ParamRegistry, fire_count: float | None, fire_history: float | None
) -> dict[str, dict[str, Any]]:
    alpha = params.require_float("P-TREND-ALPHA")
    drop = params.require_float("P-VEG-DROP")
    out: dict[str, dict[str, Any]] = {}
    frame = frame.sort_values("year")
    if len(frame) >= 5:
        ndvi = frame["ndvi"].to_numpy(dtype=float)
        lst = frame["lst_c"].to_numpy(dtype=float)
        veg = mk.original_test(ndvi)
        out["I_veg"] = {
            "value": round(float(veg.slope), 5),
            "p_value": round(float(veg.p), 5),
            "significant": bool(veg.p < alpha),
            "pct": float(np.clip(0.5 - veg.slope / (2 * _VEG_SLOPE_SCALE), 0, 1)),
            "basis": "NDVI Sen slope per year (lower = more pressure)",
        }
        heat = mk.original_test(lst)
        out["I_heat"] = {
            "value": round(float(heat.slope), 5),
            "p_value": round(float(heat.p), 5),
            "significant": bool(heat.p < alpha),
            "pct": float(np.clip(0.5 + heat.slope / (2 * _LST_SLOPE_SCALE), 0, 1)),
            "basis": "LST Sen slope °C/yr (higher = more pressure)",
        }
        previous = ndvi[:-1].mean()
        loss = max(previous - ndvi[-1], 0.0)
        out["I_loss"] = {
            "value": round(float(loss), 4),
            "significant": bool(loss > drop),
            "pct": float(np.clip(loss / (2 * drop), 0, 1)),
            "basis": f"NDVI drop vs previous mean (proxy; alert above {drop})",
            "loss_pct_of_vegetation": round(float(100.0 * loss / previous), 2)
            if previous
            else None,
        }
    if fire_count is not None and fire_history is not None and fire_history > 0:
        out["I_fire"] = {
            "value": fire_count,
            "significant": fire_count > fire_history,
            "pct": float(np.clip(fire_count / (2 * fire_history), 0, 1)),
            "basis": "vegetation-fire events vs the area's own multi-year mean",
        }
    return out


def _hpi(indicators: dict[str, dict[str, Any]], params: ParamRegistry) -> float | None:
    weights = params.require("P-HPI-W")
    keys = [k for k in indicators if indicators[k].get("pct") == indicators[k].get("pct")]
    if len(keys) < 2:
        return None
    w = {k: float(weights[k.split("_")[1]]) for k in keys}
    total = sum(w.values())
    return round(sum(w[k] * indicators[k]["pct"] for k in keys) / total, 3)


def compute_habitat_pressure(
    protected_areas: gpd.GeoDataFrame | None,
    series: pd.DataFrame | None,
    fire_events: list[FireEvent],
    params: ParamRegistry,
    utm_crs: str,
    *,
    fire_history: dict[str, float] | None = None,
) -> list[PAPressure]:
    if protected_areas is None or series is None:
        return []
    buffer_m = params.require_float("P-PA-BUFFER")
    loss_alert = params.require_float("P-LOSS-ALERT")
    pa_utm = protected_areas.to_crs(utm_crs)
    veg_fires = [
        e for e in fire_events if e.fire_class in (FireClass.VEGETATION_FIRE, FireClass.FOREST_FIRE)
    ]
    out: list[PAPressure] = []
    from pyproj import Transformer
    from shapely.geometry import Point

    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    for _, pa in pa_utm.iterrows():
        pa_id = str(pa.get("pa_id", ""))
        frame = series[series["unit_id"] == pa_id]
        if frame.empty:
            continue
        inside = near = 0
        for e in veg_fires:
            x, y = to_utm.transform(e.lon, e.lat)
            p = Point(x, y)
            if pa.geometry.contains(p):
                inside += 1
            elif pa.geometry.distance(p) <= buffer_m:
                near += 1
        history = (fire_history or {}).get(pa_id)
        indicators = _indicators_upto(frame, params, float(inside + near), history)
        hpi = _hpi(indicators, params)
        pressure = _classify(hpi, len(indicators), params)
        prev_ind = _indicators_upto(frame[frame["year"] < frame["year"].max()], params, None, None)
        prev_hpi = _hpi(prev_ind, params)
        prev_pressure = _classify(prev_hpi, len(prev_ind), params)
        warnings: list[dict[str, Any]] = []
        name = str(pa.get("name", pa_id))
        if inside:
            warnings.append(
                {
                    "code": "PA_FIRE_INSIDE",
                    "event_driven": True,
                    "count": inside,
                    "message": f"{inside} satellite fire detection(s) inside {name} (last pass)",
                }
            )
        if near:
            warnings.append(
                {
                    "code": "PA_FIRE_NEAR",
                    "event_driven": True,
                    "count": near,
                    "message": f"{near} satellite fire detection(s) within {buffer_m:.0f} m of {name}",
                }
            )
        loss = indicators.get("I_loss", {})
        rose = _RANK[pressure] > _RANK[prev_pressure] >= 0
        loss_pct = loss.get("loss_pct_of_vegetation")
        if rose or (loss_pct is not None and loss_pct > loss_alert and loss.get("significant")):
            warnings.append(
                {
                    "code": "PA_HABITAT_PRESSURE_RISE",
                    "event_driven": False,
                    "audience": "environment and forest officers (not public)",
                    "message": f"habitat pressure indicator for {name} rose; {DISCLAIMER}",
                }
            )
        out.append(PAPressure(pa_id, name, hpi, pressure, indicators, prev_pressure, warnings))
    return _rank_across_areas(out, params) if len(out) >= 3 else out


def _rank_across_areas(areas: list[PAPressure], params: ParamRegistry) -> list[PAPressure]:
    """With ≥3 areas, indicators become percentiles across the region (spec M23)."""
    for key, worse_is_higher in (
        ("I_fire", True),
        ("I_loss", True),
        ("I_veg", False),
        ("I_heat", True),
    ):
        have = [a for a in areas if key in a.indicators]
        if len(have) < 3:
            continue
        values = np.array([a.indicators[key]["value"] for a in have], dtype=float)
        order = values.argsort().argsort() / (len(values) - 1)
        for a, pct in zip(have, order, strict=True):
            a.indicators[key]["pct"] = float(pct if worse_is_higher else 1 - pct)
            a.indicators[key]["basis"] += "; percentile across protected areas"
    for a in areas:
        a.hpi = _hpi(a.indicators, params)
        a.pressure = _classify(a.hpi, len(a.indicators), params)
    return areas


def ward_pressure_table(
    pressures: list[PAPressure],
    protected_areas: gpd.GeoDataFrame | None,
    wards_utm: gpd.GeoDataFrame,
    ward_ids: list[str],
) -> pd.DataFrame | None:
    """hazards.* fields: overlap share, nearest distance, maximum pressure class touching."""
    if protected_areas is None:
        return None
    pa_utm = protected_areas.to_crs(wards_utm.crs)
    by_id = {p.pa_id: p for p in pressures}
    rows: dict[str, dict[str, Any]] = {}
    for wid, geom in zip(ward_ids, wards_utm.geometry, strict=True):
        overlap = 0.0
        nearest = float("inf")
        worst = HabitatPressure.INSUFFICIENT_DATA
        for _, pa in pa_utm.iterrows():
            nearest = min(nearest, float(geom.distance(pa.geometry)))
            share = geom.intersection(pa.geometry).area / geom.area if geom.area else 0.0
            overlap += share
            pressure = by_id.get(str(pa.get("pa_id", "")))
            if share > 0 and pressure and _RANK[pressure.pressure] > _RANK[worst]:
                worst = pressure.pressure
        rows[wid] = {
            "protected_area_overlap": round(min(overlap, 1.0), 4),
            "nearest_protected_area_m": round(nearest, 0),
            "habitat_pressure_max": worst.value
            if worst is not HabitatPressure.INSUFFICIENT_DATA
            else None,
        }
    return pd.DataFrame.from_dict(rows, orient="index")
