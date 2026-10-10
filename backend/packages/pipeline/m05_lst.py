"""M5 Land Surface Temperature from the USGS L2 ST product (no single-channel / split-window).

Per pixel: seasonal median, p90, number of valid observations, IQR, per-year
medians, and per-scene ``hot_flag = LST > city p90``. A plausible-range filter
removes impossible values and logs the share removed. °C is for display only.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.pipeline.grid import FloatArray
from packages.pipeline.m03_landsat import SceneStack

__all__ = ["KELVIN_OFFSET", "LSTResult", "compute_lst"]

KELVIN_OFFSET = 273.15
_log = get_logger("pipeline.m05")


@dataclass
class LSTResult:
    median_c: FloatArray
    p90_c: FloatArray
    iqr_c: FloatArray
    n_obs: NDArray[np.int64]
    per_year_median_c: dict[int, FloatArray]
    scenes_c: FloatArray  # (n_scenes, h, w) after the range filter
    hot_flags: NDArray[np.bool_]  # (n_scenes, h, w): LST > city p90 in that scene
    removed_out_of_range_pct: float


def _nan_reduce(fn: object, *args: object, **kwargs: object) -> FloatArray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN slices are expected
        return fn(*args, **kwargs)  # type: ignore[operator, no-any-return]


def compute_lst(
    stack: SceneStack, params: ParamRegistry, city_mask: NDArray[np.bool_]
) -> LSTResult:
    """Seasonal LST statistics. ``city_mask`` marks pixels inside the analysis units."""
    rng = params.require("P-LST-RANGE")
    scenes_c = stack.st_kelvin - KELVIN_OFFSET
    finite_before = int(np.isfinite(scenes_c).sum())
    implausible = (scenes_c < float(rng["min_c"])) | (scenes_c > float(rng["max_c"]))
    scenes_c = np.where(implausible, np.nan, scenes_c)
    removed = int(np.isfinite(stack.st_kelvin).sum()) - int(np.isfinite(scenes_c).sum())
    removed_pct = round(100.0 * removed / finite_before, 3) if finite_before else 0.0
    _log.info("lst_range_filter", removed_pct=removed_pct)

    median = _nan_reduce(np.nanmedian, scenes_c, axis=0)
    p90 = _nan_reduce(np.nanpercentile, scenes_c, 90, axis=0)
    q75, q25 = (_nan_reduce(np.nanpercentile, scenes_c, q, axis=0) for q in (75, 25))
    n_obs = np.isfinite(scenes_c).sum(axis=0).astype(np.int64)

    years = stack.years()
    per_year = {
        int(y): _nan_reduce(np.nanmedian, scenes_c[years == y], axis=0) for y in np.unique(years)
    }

    hot = np.zeros(scenes_c.shape, dtype=bool)
    for k in range(scenes_c.shape[0]):
        inside = scenes_c[k][city_mask & np.isfinite(scenes_c[k])]
        if inside.size:
            hot[k] = scenes_c[k] > np.percentile(inside, 90)

    return LSTResult(median, p90, q75 - q25, n_obs, per_year, scenes_c, hot, removed_pct)
