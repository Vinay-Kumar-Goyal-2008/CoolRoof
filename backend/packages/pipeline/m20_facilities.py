"""M20 Facility counts and coverage per ward (the data half of hospital readiness).

``nearest_hospital_m`` is measured (straight line) from the exposed-population-weighted
centroid of the ward; ``facilities_per_10k_exposed = 10000 · hospitals within P-COVER ÷ exposed``.
The request-time readiness prompts live in ``services/m20_readiness.py``.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from packages.core.params import ParamRegistry

__all__ = ["facility_table", "weighted_centroids"]


def weighted_centroids(
    buildings: gpd.GeoDataFrame | None,
    building_pop: pd.Series | None,
    wards_utm: gpd.GeoDataFrame,
    ward_ids: list[str],
) -> dict[str, tuple[float, float, str]]:
    """Ward → (x, y, method). Population-weighted when buildings and people are known."""
    out: dict[str, tuple[float, float, str]] = {}
    for wid, geom in zip(ward_ids, wards_utm.geometry, strict=True):
        c = geom.centroid
        out[wid] = (float(c.x), float(c.y), "ward_centroid")
    if buildings is None or building_pop is None or buildings.empty:
        return out
    pts = buildings.geometry.centroid
    weights = building_pop.reindex(buildings.building_id).fillna(0.0).to_numpy()
    for wid in ward_ids:
        mask = (buildings.ward_id == wid).to_numpy()
        w = weights[mask]
        if mask.sum() and w.sum() > 0:
            out[wid] = (
                float(np.average(pts[mask].x, weights=w)),
                float(np.average(pts[mask].y, weights=w)),
                "population_weighted",
            )
    return out


def facility_table(
    facilities: gpd.GeoDataFrame | None,
    wards_utm: gpd.GeoDataFrame,
    ward_ids: list[str],
    centroids: dict[str, tuple[float, float, str]],
    exposed: pd.Series | None,
    params: ParamRegistry,
) -> pd.DataFrame | None:
    """Per-ward infrastructure table; ``None`` when no facility dataset was provided."""
    if facilities is None:
        return None
    cover = params.require_float("P-COVER")
    fac = facilities.to_crs(wards_utm.crs)
    kinds = fac["kind"].astype(str)
    rows: dict[str, dict[str, float | None]] = {}
    hospitals = fac[kinds == "hospital"]
    for wid, geom in zip(ward_ids, wards_utm.geometry, strict=True):
        inside = fac[fac.within(geom)]
        k = inside["kind"].astype(str)
        row: dict[str, float | None] = {
            "hospital_count": float((k == "hospital").sum()),
            "school_count": float((k == "school").sum()),
            "cooling_point_count": float((k == "cooling_point").sum()),
            "nearest_hospital_m": None,
            "facilities_per_10k_exposed": None,
        }
        cx, cy, _ = centroids[wid]
        if len(hospitals):
            dist = np.hypot(hospitals.geometry.x - cx, hospitals.geometry.y - cy)
            row["nearest_hospital_m"] = float(dist.min())
            exp = float(exposed.get(wid, np.nan)) if exposed is not None else np.nan
            if np.isfinite(exp) and exp > 0:
                row["facilities_per_10k_exposed"] = 10000.0 * float((dist <= cover).sum()) / exp
        rows[wid] = row
    return pd.DataFrame.from_dict(rows, orient="index")
