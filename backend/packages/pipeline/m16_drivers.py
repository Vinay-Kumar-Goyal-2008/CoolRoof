"""M16 Heat tracing: which land features are *associated with* a ward's heat (correlational).

Blocks of N×N pixels (water removed) → features (NDVI, NDBI, built fraction, roof fraction,
distance to water, elevation, slope) → VIF filter → standardised OLS (robust SE) plus gradient
boosting with SHAP. If the two disagree on a driver's sign, the driver is flagged ``unstable``.
Validation is spatial: leave-out 2 km tiles with a buffer; R² and Moran's I of residuals are
reported. A ward's contribution is the mean SHAP value over its blocks, with a bootstrap CI.

Wording is always "associated with" — never "caused by" (see ``core.wording``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy import ndimage
from scipy.spatial import cKDTree

from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.pipeline.grid import FloatArray, Grid
from packages.pipeline.landcover import WorldCover

__all__ = ["DriverResult", "WardDrivers", "attribute_drivers"]

_log = get_logger("pipeline.m16")

UNOBSERVED = ["anthropogenic_heat", "industrial_process_heat", "roof_material"]
FEATURE_LABELS = {
    "ndvi": ("vegetation (NDVI)", "वनस्पति (NDVI)"),
    "ndbi": ("built-up index (NDBI)", "निर्मित क्षेत्र सूचकांक (NDBI)"),
    "built_fraction": ("built-up land share", "निर्मित भूमि का हिस्सा"),
    "roof_fraction": ("roof coverage", "छत का आवरण"),
    "water_distance_km": ("distance to water", "जल से दूरी"),
    "elevation_m": ("elevation", "ऊँचाई"),
    "slope_deg": ("slope", "ढलान"),
}


@dataclass(frozen=True)
class WardDrivers:
    ward_id: str
    status: str  # "ok" | "outside_model_support" | "too_few_blocks"
    drivers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def top(self) -> list[dict[str, Any]]:
        return sorted(self.drivers, key=lambda d: -abs(d["contribution_c"]))[:3]


@dataclass
class DriverResult:
    wards: dict[str, WardDrivers]
    model_card: dict[str, Any]


def _block_mean(a: NDArray[Any], n: int) -> FloatArray:
    h, w = (a.shape[0] // n) * n, (a.shape[1] // n) * n
    view = a[:h, :w].reshape(h // n, n, w // n, n).astype(np.float64)
    with np.errstate(all="ignore"):
        return np.nanmean(view, axis=(1, 3))  # type: ignore[no-any-return]


def _vif(x: NDArray[np.float64]) -> NDArray[np.float64]:
    out = np.empty(x.shape[1])
    for j in range(x.shape[1]):
        others = np.delete(x, j, axis=1)
        design = np.column_stack([np.ones(len(x)), others])
        coef, *_ = np.linalg.lstsq(design, x[:, j], rcond=None)
        resid = x[:, j] - design @ coef
        ss_tot = float(np.sum((x[:, j] - x[:, j].mean()) ** 2))
        r2 = 1 - float(np.sum(resid**2)) / ss_tot if ss_tot > 0 else 0.0
        out[j] = 1 / max(1 - r2, 1e-6)
    return out


def vif_filter(frame: pd.DataFrame, vif_max: float) -> tuple[list[str], list[str]]:
    """Drop the highest-VIF feature until all are ≤ ``vif_max`` (NDVI/NDBI collinearity)."""
    keep = list(frame.columns)
    dropped: list[str] = []
    while len(keep) > 2:
        vif = _vif(frame[keep].to_numpy())
        worst = int(np.argmax(vif))
        if vif[worst] <= vif_max:
            break
        if keep[worst] == "ndvi" and "ndbi" in keep:  # collinear pair: keep the vegetation index
            worst = keep.index("ndbi")
        dropped.append(keep.pop(worst))
    return keep, dropped


def morans_i(xy: NDArray[np.float64], values: NDArray[np.float64], k: int = 8) -> float:
    """Moran's I with k-nearest-neighbour weights (row-standardised)."""
    n = len(values)
    if n <= k + 1:
        return float("nan")
    tree = cKDTree(xy)
    _, idx = tree.query(xy, k=k + 1)
    z = values - values.mean()
    denom = float(np.sum(z**2))
    if denom == 0:
        return float("nan")
    num = float(np.sum(z[:, None] * z[idx[:, 1:]]) / k)
    return num / denom


def _spatial_cv(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    xy: NDArray[np.float64],
    tile_km: float,
    buffer_km: float,
    seed: int,
) -> tuple[float, NDArray[np.float64]]:
    """Leave-out-tiles CV with a training buffer. Returns (R², out-of-fold residuals)."""
    import xgboost as xgb

    tile = (
        np.floor(xy[:, 0] / (tile_km * 1000)) * 1000 + np.floor(xy[:, 1] / (tile_km * 1000))
    ).astype(np.int64)
    tiles = np.unique(tile)
    rng = np.random.default_rng(seed)
    rng.shuffle(tiles)
    folds = np.array_split(tiles, min(5, len(tiles)))
    pred = np.full(len(y), np.nan)
    for fold in folds:
        test = np.isin(tile, fold)
        if test.sum() == 0 or (~test).sum() < 50:
            continue
        near = cKDTree(xy[test]).query(xy, distance_upper_bound=buffer_km * 1000)[0] < np.inf
        train = ~test & ~near
        if train.sum() < 50:
            train = ~test
        model = xgb.XGBRegressor(
            n_estimators=120, max_depth=4, learning_rate=0.1, subsample=0.8, random_state=seed
        )
        model.fit(x[train], y[train])
        pred[test] = model.predict(x[test])
    ok = np.isfinite(pred)
    if ok.sum() < 10:
        return float("nan"), np.full(len(y), np.nan)
    resid = y - pred
    ss_res = float(np.sum(resid[ok] ** 2))
    ss_tot = float(np.sum((y[ok] - y[ok].mean()) ** 2))
    return (1 - ss_res / ss_tot if ss_tot > 0 else float("nan")), resid


def _block_features(
    grid: Grid,
    ndvi: FloatArray,
    ndbi: FloatArray,
    landcover: NDArray[np.int64],
    dem: FloatArray | None,
    roofs: gpd.GeoDataFrame | None,
    n: int,
) -> dict[str, FloatArray]:
    built = (landcover == WorldCover.BUILT).astype(np.float64)
    water = np.isin(landcover, (WorldCover.WATER,)).astype(np.float64)
    dist_water = (
        ndimage.distance_transform_edt(water == 0, sampling=grid.resolution_m) / 1000.0
        if water.any()
        else np.full(grid.shape, np.nan)
    )
    feats: dict[str, FloatArray] = {
        "ndvi": _block_mean(ndvi, n),
        "ndbi": _block_mean(ndbi, n),
        "built_fraction": _block_mean(built, n),
        "water_distance_km": _block_mean(dist_water, n),
    }
    if roofs is not None and len(roofs):
        from rasterio.features import rasterize

        roof_mask = rasterize(
            ((g, 1) for g in roofs.to_crs(grid.crs).geometry),
            out_shape=grid.shape,
            transform=grid.transform,
            fill=0,
            dtype="uint8",
        )
        feats["roof_fraction"] = _block_mean(roof_mask, n)
    if dem is not None:
        gy, gx = np.gradient(dem, grid.resolution_m)
        feats["elevation_m"] = _block_mean(dem, n)
        feats["slope_deg"] = _block_mean(np.degrees(np.arctan(np.hypot(gx, gy))), n)
    feats["_water_share"] = _block_mean(water, n)
    return feats


def attribute_drivers(
    grid: Grid,
    dlst_c: FloatArray,
    ndvi: FloatArray,
    ndbi: FloatArray,
    landcover: NDArray[np.int64] | None,
    dem: FloatArray | None,
    roofs: gpd.GeoDataFrame | None,
    wards_utm: gpd.GeoDataFrame,
    ward_ids: list[str],
    params: ParamRegistry,
    *,
    seed: int = 20261010,
) -> DriverResult | None:
    """Per-ward driver contributions (°C of ΔLST, direction, bootstrap CI)."""
    import shap
    import statsmodels.api as sm
    import xgboost as xgb

    if landcover is None:
        _log.warning("drivers_skipped", reason="no land cover")
        return None
    n = int(params.require("P-DRIVER-BLOCK"))
    cv_cfg = params.require("P-DRIVER-CV")
    feats = _block_features(grid, ndvi, ndbi, landcover, dem, roofs, n)
    water_share = feats.pop("_water_share")
    y_block = _block_mean(dlst_c, n)
    frame = pd.DataFrame({k: v.ravel() for k, v in feats.items()})
    frame["y"] = y_block.ravel()
    xs, ys = grid.pixel_centers()
    cx, cy = (
        xs[1::n, 1::n][: y_block.shape[0], : y_block.shape[1]],
        ys[1::n, 1::n][: y_block.shape[0], : y_block.shape[1]],
    )
    ids = grid.rasterize_ids(wards_utm)
    frame["ward_idx"] = ids[1::n, 1::n][: y_block.shape[0], : y_block.shape[1]].ravel()
    frame["x"], frame["y_m"] = cx.ravel(), cy.ravel()
    frame["water"] = water_share.ravel()
    frame = frame[frame["water"] < 0.5].drop(columns="water")
    frame = frame.dropna(subset=[c for c in frame.columns if c != "ward_idx"])
    if len(frame) < 200:
        _log.warning("drivers_skipped", reason="too few blocks", n=len(frame))
        return None

    names = [c for c in feats if c != "_water_share" and frame[c].std() > 0]
    kept, dropped = vif_filter(frame[names], float(cv_cfg["vif_max"]))
    x_raw = frame[kept].to_numpy()
    mu, sd = x_raw.mean(axis=0), x_raw.std(axis=0)
    x = (x_raw - mu) / sd
    y = frame["y"].to_numpy()
    xy = frame[["x", "y_m"]].to_numpy()

    ols = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HC3")
    ols_coef = dict(zip(kept, ols.params[1:], strict=True))

    gbm = xgb.XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.08, subsample=0.8, random_state=seed
    )
    gbm.fit(x, y)
    shap_values = np.asarray(shap.TreeExplainer(gbm).shap_values(x))

    # Direction of each feature in the GBM: sign of corr(feature, SHAP)
    gbm_sign = {
        f: float(np.sign(np.corrcoef(x[:, j], shap_values[:, j])[0, 1]))
        if shap_values[:, j].std() > 0
        else 0.0
        for j, f in enumerate(kept)
    }
    stable = {f: bool(np.sign(ols_coef[f]) == gbm_sign[f] or gbm_sign[f] == 0.0) for f in kept}

    r2_cv, resid = _spatial_cv(x, y, xy, float(cv_cfg["tile_km"]), float(cv_cfg["buffer_km"]), seed)
    ok = np.isfinite(resid)
    moran = morans_i(xy[ok], resid[ok]) if ok.sum() > 50 else float("nan")

    lo, hi = np.percentile(x_raw, 1, axis=0), np.percentile(x_raw, 99, axis=0)
    rng = np.random.default_rng(seed)
    boot = int(cv_cfg["bootstrap"])
    out: dict[str, WardDrivers] = {}
    for idx, wid in enumerate(ward_ids):
        rows = np.flatnonzero(frame["ward_idx"].to_numpy() == idx)
        if len(rows) < 10:
            out[wid] = WardDrivers(wid, "too_few_blocks")
            continue
        ward_mean = x_raw[rows].mean(axis=0)
        if np.any(ward_mean < lo) or np.any(ward_mean > hi):
            out[wid] = WardDrivers(wid, "outside_model_support")
            continue
        sv = shap_values[rows]
        mean_sv = sv.mean(axis=0)
        draws = rng.integers(0, len(rows), size=(boot, len(rows)))
        boot_means = sv[draws].mean(axis=1)  # (boot, features)
        ci = np.percentile(boot_means, [2.5, 97.5], axis=0)
        drivers = [
            {
                "feature": f,
                "label": {"en": FEATURE_LABELS[f][0], "hi": FEATURE_LABELS[f][1]},
                "contribution_c": round(float(mean_sv[j]), 3),
                "direction": "warmer" if mean_sv[j] > 0 else "cooler",
                "ci_low": round(float(ci[0, j]), 3),
                "ci_high": round(float(ci[1, j]), 3),
                "stable": stable[kept[j]],
            }
            for j, f in enumerate(kept)
        ]
        out[wid] = WardDrivers(wid, "ok", drivers)
    card = {
        "method": "OLS (standardised, HC3 robust SE) + XGBoost with SHAP",
        "block_pixels": n,
        "n_blocks": len(frame),
        "features_used": kept,
        "features_dropped_vif": dropped,
        "ols_coefficients_c_per_sd": {f: round(float(v), 3) for f, v in ols_coef.items()},
        "ols_r2": round(float(ols.rsquared), 3),
        "gbm_spatial_cv_r2": None if np.isnan(r2_cv) else round(float(r2_cv), 3),
        "residual_morans_i": None if np.isnan(moran) else round(float(moran), 3),
        "unobserved": UNOBSERVED,
        "wording": "associated with — correlational, not causal",
    }
    return DriverResult(out, card)
