"""M6 Heat / heat-island analysis.

* ΔLST = LST − median LST over a rural reference mask (cropland/tree in a ring
  around the city, excluding water and steep terrain), elevation-adjusted when
  city relief is large. An empty mask widens the ring, then falls back to a
  labelled city-percentile baseline.
* Area-weighted zonal stats per ward, hotspots (percentile + connected
  components), persistence (mean share of ward area in the city top decile per
  scene), ``heat_z``, and NDVI/NDBI/NDWI/BSI composites.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from rasterio.features import shapes
from scipy import ndimage, stats
from shapely.geometry import shape

from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.pipeline.grid import FloatArray, Grid, zonal_stats
from packages.pipeline.landcover import WorldCover
from packages.pipeline.m03_landsat import SceneStack
from packages.pipeline.m05_lst import LSTResult

__all__ = ["HeatFeatures", "ReferenceInfo", "compute_heat", "rank_stability_leave_one_year_out"]

_log = get_logger("pipeline.m06")


@dataclass(frozen=True)
class ReferenceInfo:
    method: str  # "rural_ring" | "city_percentile_baseline"
    reference_lst_c: float
    n_pixels: int
    ring_km: tuple[float, float] | None
    elevation_adjusted: bool


@dataclass
class HeatFeatures:
    """Per-ward heat table plus rasters and hotspots."""

    table: pd.DataFrame  # index: ward_id
    dlst_c: FloatArray
    ndvi: FloatArray
    reference: ReferenceInfo
    hotspots: gpd.GeoDataFrame
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _nanmedian(a: FloatArray, axis: int = 0) -> FloatArray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(a, axis=axis)  # type: ignore[no-any-return]


def _slope_deg(dem: FloatArray, res_m: float) -> FloatArray:
    gy, gx = np.gradient(dem, res_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))  # type: ignore[no-any-return]


def _reference(
    lst_c: FloatArray,
    landcover: NDArray[np.int64] | None,
    dem: FloatArray | None,
    city_mask: NDArray[np.bool_],
    grid: Grid,
    params: ParamRegistry,
) -> tuple[NDArray[np.bool_] | None, ReferenceInfo, FloatArray]:
    """Reference mask, its info, and the (possibly elevation-adjusted) LST."""
    ring = params.require("P-REF-RING")
    relief = params.require("P-RELIEF")
    max_slope = params.require_float("P-REF-MAXSLOPE")

    adjusted = lst_c
    elevation_adjusted = False
    if dem is not None and np.isfinite(dem).any():
        lo, hi = np.nanpercentile(dem, [5, 95])
        if hi - lo > float(relief["relief_threshold_m"]):
            adjusted = lst_c + float(relief["lapse_rate_c_per_km"]) / 1000.0 * (
                dem - np.nanmedian(dem[city_mask])
            )
            elevation_adjusted = True

    if landcover is not None:
        dist_km = ndimage.distance_transform_edt(~city_mask) * grid.resolution_m / 1000.0
        candidate = np.isin(landcover, [int(c) for c in WorldCover.rural_reference()])
        if dem is not None:
            candidate &= _slope_deg(dem, grid.resolution_m) <= max_slope
        candidate &= np.isfinite(adjusted)
        inner, outer = float(ring["inner_km"]), float(ring["outer_km"])
        for _ in range(int(ring["max_widen"]) + 1):
            mask = candidate & (dist_km >= inner) & (dist_km <= outer)
            if int(mask.sum()) >= int(ring["min_pixels"]):
                ref = float(np.median(adjusted[mask]))
                return (
                    mask,
                    ReferenceInfo(
                        "rural_ring", ref, int(mask.sum()), (inner, outer), elevation_adjusted
                    ),
                    adjusted,
                )
            outer *= float(ring["widen_factor"])

    # Fallback: labelled city-percentile baseline (spec M6 edge case).
    city_vals = adjusted[city_mask & np.isfinite(adjusted)]
    ref = float(np.percentile(city_vals, float(ring["fallback_city_pct"])))
    _log.warning("reference_fallback_city_percentile", reference_c=ref)
    return (
        None,
        ReferenceInfo(
            "city_percentile_baseline", ref, int(city_vals.size), None, elevation_adjusted
        ),
        adjusted,
    )


def _hotspots(
    dlst: FloatArray,
    city_mask: NDArray[np.bool_],
    ward_idx: NDArray[np.int32],
    ward_ids: list[str],
    landcover: NDArray[np.int64] | None,
    grid: Grid,
    params: ParamRegistry,
) -> gpd.GeoDataFrame:
    cfg = params.require("P-HOTSPOT-PCT")
    vals = dlst[city_mask & np.isfinite(dlst)]
    columns = [
        "hotspot_id",
        "ward_id",
        "n_pixels",
        "area_m2",
        "mean_dlst_c",
        "max_dlst_c",
        "built_share",
        "bare_share",
        "geometry",
    ]
    if vals.size == 0:
        return gpd.GeoDataFrame(columns=columns, geometry="geometry", crs=grid.crs)
    threshold = float(np.quantile(vals, float(cfg["pct"])))
    hot = city_mask & np.isfinite(dlst) & (dlst >= threshold)
    labels, n = ndimage.label(hot, structure=np.ones((3, 3)))
    rows: list[dict[str, Any]] = []
    for label in range(1, n + 1):
        comp = labels == label
        size = int(comp.sum())
        if size < int(cfg["min_pixels"]):
            continue
        owners = ward_idx[comp]
        owner = int(np.bincount(owners[owners >= 0]).argmax())
        geoms = [
            shape(g)
            for g, v in shapes(comp.astype(np.uint8), mask=comp, transform=grid.transform)
            if v == 1
        ]
        lc = landcover[comp] if landcover is not None else np.array([])
        rows.append(
            {
                "hotspot_id": f"H{label:04d}",
                "ward_id": ward_ids[owner],
                "n_pixels": size,
                "area_m2": size * grid.pixel_area_m2,
                "mean_dlst_c": float(np.mean(dlst[comp])),
                "max_dlst_c": float(np.max(dlst[comp])),
                "built_share": float(np.mean(lc == WorldCover.BUILT)) if lc.size else np.nan,
                "bare_share": float(np.mean(lc == WorldCover.BARE)) if lc.size else np.nan,
                "geometry": gpd.GeoSeries(geoms).union_all(),
            }
        )
    return gpd.GeoDataFrame(rows, columns=columns, geometry="geometry", crs=grid.crs)


def compute_heat(
    stack: SceneStack,
    lst: LSTResult,
    wards_utm: gpd.GeoDataFrame,
    landcover: NDArray[np.int64] | None,
    dem: FloatArray | None,
    params: ParamRegistry,
) -> HeatFeatures:
    """Run M6 on gridded inputs (``landcover`` / ``dem`` may be None → fallbacks)."""
    grid = stack.grid
    ward_ids = list(wards_utm.ward_id)
    ward_idx = grid.rasterize_ids(wards_utm)
    city_mask = ward_idx >= 0

    _ref_mask, ref_info, adjusted = _reference(
        lst.median_c, landcover, dem, city_mask, grid, params
    )
    dlst = adjusted - ref_info.reference_lst_c

    zs = zonal_stats(
        grid, dlst, wards_utm, ["mean", "median", "quantile(q=0.9)", "max", "stdev", "count"]
    )
    lst_p90 = zonal_stats(grid, lst.median_c, wards_utm, ["quantile(q=0.9)"])
    nobs = zonal_stats(grid, lst.n_obs.astype(np.float64), wards_utm, ["median"])

    table = pd.DataFrame(index=pd.Index(ward_ids, name="ward_id"))
    table["mean_dlst_c"] = zs["mean"].to_numpy()
    table["median_dlst_c"] = zs["median"].to_numpy()
    table["p90_dlst_c"] = zs["quantile_90"].to_numpy()
    table["max_dlst_c"] = zs["max"].to_numpy()
    table["std_dlst_c"] = zs["stdev"].to_numpy()
    table["valid_pixels"] = zs["count"].to_numpy()
    table["p90_lst_c"] = lst_p90["quantile_90"].to_numpy()
    table["n_obs"] = nobs["median"].to_numpy()
    table["low_confidence"] = table["n_obs"] < params.require_float("P-MINOBS")

    # Persistence: mean share of ward area in the city's top decile per scene.
    shares = []
    for k in range(lst.hot_flags.shape[0]):
        flag = np.where(np.isfinite(lst.scenes_c[k]), lst.hot_flags[k].astype(np.float64), np.nan)
        shares.append(zonal_stats(grid, flag, wards_utm, ["mean"])["mean"].to_numpy())
    table["persistence"] = np.nanmean(np.vstack(shares), axis=0) if shares else np.nan

    mu, sigma = table["mean_dlst_c"].mean(), table["mean_dlst_c"].std(ddof=0)
    table["heat_z"] = (table["mean_dlst_c"] - mu) / sigma if sigma > 0 else 0.0

    composites = {
        name: _nanmedian(getattr(stack, name)) for name in ("ndvi", "ndbi", "ndwi", "bsi")
    }
    for name, arr in composites.items():
        table[f"{name}_mean"] = zonal_stats(grid, arr, wards_utm, ["mean"])["mean"].to_numpy()

    if landcover is not None:
        for cls, col in (
            (WorldCover.BUILT, "wc_built_fraction"),
            (WorldCover.BARE, "bare_fraction"),
            (WorldCover.TREE, "tree_fraction"),
            (WorldCover.WATER, "water_fraction"),
        ):
            ind = (landcover == cls).astype(np.float64)
            table[col] = zonal_stats(grid, ind, wards_utm, ["mean"])["mean"].to_numpy()
        water = landcover == WorldCover.WATER
        if water.any():
            dist = ndimage.distance_transform_edt(~water) * grid.resolution_m
            table["water_distance_m"] = zonal_stats(grid, dist, wards_utm, ["mean"])[
                "mean"
            ].to_numpy()
    if dem is not None:
        table["elevation_mean_m"] = zonal_stats(grid, dem, wards_utm, ["mean"])["mean"].to_numpy()

    table["area_m2"] = wards_utm.geometry.area.to_numpy()
    table["ward_too_small"] = table["area_m2"] < params.require_float("P-WARD-MINAREA")

    hotspots = _hotspots(dlst, city_mask, ward_idx, ward_ids, landcover, grid, params)
    diagnostics = {
        "city_mean_heat_z": float(table["heat_z"].mean()),
        "reference_pixels": ref_info.n_pixels,
        "hotspot_count": len(hotspots),
        "hotspot_built_or_bare_share": float(
            ((hotspots["built_share"] + hotspots["bare_share"]) * hotspots["n_pixels"]).sum()
            / hotspots["n_pixels"].sum()
        )
        if len(hotspots)
        else None,
        "removed_out_of_range_pct": lst.removed_out_of_range_pct,
    }
    _log.info("heat_features", **{k: v for k, v in diagnostics.items() if v is not None})
    return HeatFeatures(table, dlst, composites["ndvi"], ref_info, hotspots, diagnostics)


def rank_stability_leave_one_year_out(
    lst: LSTResult, reference_c: float, grid: Grid, wards_utm: gpd.GeoDataFrame
) -> dict[int, float]:
    """Kendall τ between full-period ward ranks and ranks with each year left out (M6 Verify)."""
    full = zonal_stats(grid, lst.median_c - reference_c, wards_utm, ["mean"])["mean"].to_numpy()
    taus: dict[int, float] = {}
    years = sorted(lst.per_year_median_c)
    for left_out in years:
        kept = [lst.per_year_median_c[y] for y in years if y != left_out]
        if not kept:
            continue
        partial = _nanmedian(np.stack(kept)) - reference_c
        loo = zonal_stats(grid, partial, wards_utm, ["mean"])["mean"].to_numpy()
        tau = stats.kendalltau(full, loo).statistic
        taus[left_out] = float(tau)
    return taus
