"""M3+4 Landsat acquisition and preprocessing.

For every scene in the hot-season windows: windowed read of ST, ST_QA, QA_PIXEL
and SR bands reprojected onto the common grid, QA_PIXEL masking (fill, dilated
cloud, cirrus, cloud, shadow, snow), scale/offset from STAC metadata, and
dropping pixels whose ST uncertainty exceeds ``P-STQA``.

Output: a masked surface-temperature stack (Kelvin), per-scene spectral indices,
and a scene manifest with valid-pixel percentages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from numpy.typing import NDArray
from rasterio.enums import Resampling

from packages.adapters.landsat_source import LandsatSource, SceneItem
from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.pipeline.grid import FloatArray, Grid, warp_to_grid

__all__ = ["QA_MASK_BITS", "SceneRecord", "SceneStack", "preprocess", "season_windows"]

_log = get_logger("pipeline.m03")

# QA_PIXEL bits that invalidate a pixel [R: Landsat C2 L2 product guide]
QA_MASK_BITS: dict[str, int] = {
    "fill": 0,
    "dilated_cloud": 1,
    "cirrus": 2,
    "cloud": 3,
    "cloud_shadow": 4,
    "snow": 5,
}
_QA_MASK = sum(1 << b for b in QA_MASK_BITS.values())


@dataclass(frozen=True)
class SceneRecord:
    scene_id: str
    acquired: date
    platform: str
    cloud_cover: float
    valid_pixel_pct: float


@dataclass
class SceneStack:
    """Masked, gridded scenes. Arrays are (n_scenes, height, width), NaN = invalid."""

    grid: Grid
    st_kelvin: FloatArray
    ndvi: FloatArray
    ndbi: FloatArray
    ndwi: FloatArray
    bsi: FloatArray
    scenes: list[SceneRecord] = field(default_factory=list)

    @property
    def n_scenes(self) -> int:
        return len(self.scenes)

    def years(self) -> NDArray[np.int64]:
        return np.array([s.acquired.year for s in self.scenes])


def season_windows(
    params: ParamRegistry, today: date, years: list[int] | int
) -> list[tuple[date, date]]:
    """Hot-season windows: explicit years, or the last N completed/ongoing seasons."""
    season = params.require("P-SEASON")
    sm, sd = (int(v) for v in str(season["start_mmdd"]).split("-"))
    em, ed = (int(v) for v in str(season["end_mmdd"]).split("-"))
    if isinstance(years, int):
        latest = today.year if today >= date(today.year, sm, sd) else today.year - 1
        year_list = list(range(latest - years + 1, latest + 1))
    else:
        year_list = list(years)
    return [(date(y, sm, sd), date(y, em, ed)) for y in year_list]


def _scaled(
    raw: NDArray[np.float64], scale: float, offset: float, nodata: float | None
) -> FloatArray:
    out = raw.astype(np.float64) * scale + offset
    if nodata is not None:
        out[raw == nodata] = np.nan
    return out


def _ratio(a: FloatArray, b: FloatArray) -> FloatArray:
    with np.errstate(divide="ignore", invalid="ignore"):
        den = a + b
        out = (a - b) / den
    out[~np.isfinite(out)] = np.nan
    return out


def _read_scene(item: SceneItem, grid: Grid, stqa_max_k: float) -> dict[str, FloatArray]:
    bands = item.bands
    qa_ref = bands["qa_pixel"]
    qa = warp_to_grid(qa_ref.href, grid, resampling=Resampling.nearest)
    qa_nodata = qa_ref.nodata
    invalid = (qa.astype(np.int64) & _QA_MASK) != 0
    if qa_nodata is not None:
        invalid |= qa == qa_nodata

    st_ref = bands["st"]
    st = _scaled(warp_to_grid(st_ref.href, grid), st_ref.scale, st_ref.offset, st_ref.nodata)
    if "st_qa" in bands:
        q = bands["st_qa"]
        unc = _scaled(
            warp_to_grid(q.href, grid, resampling=Resampling.nearest), q.scale, q.offset, q.nodata
        )
        invalid |= ~(unc <= stqa_max_k)  # also drops pixels with unknown uncertainty
    st[invalid] = np.nan

    sr: dict[str, FloatArray] = {}
    for name in ("blue", "green", "red", "nir", "swir1"):
        if name in bands:
            ref = bands[name]
            arr = _scaled(warp_to_grid(ref.href, grid), ref.scale, ref.offset, ref.nodata)
            arr[invalid] = np.nan
            sr[name] = arr
    out = {"st": st}
    if {"red", "nir"} <= sr.keys():
        out["ndvi"] = _ratio(sr["nir"], sr["red"])
    if {"swir1", "nir"} <= sr.keys():
        out["ndbi"] = _ratio(sr["swir1"], sr["nir"])
    if {"green", "nir"} <= sr.keys():
        out["ndwi"] = _ratio(sr["green"], sr["nir"])
    if {"swir1", "red", "nir", "blue"} <= sr.keys():
        out["bsi"] = _ratio(sr["swir1"] + sr["red"], sr["nir"] + sr["blue"])
    return out


def preprocess(
    source: LandsatSource,
    grid: Grid,
    bbox_lonlat: tuple[float, float, float, float],
    windows: list[tuple[date, date]],
    params: ParamRegistry,
) -> SceneStack:
    """Search, read, mask and grid every scene in the season windows."""
    max_cloud = params.require_float("P-MAXCLOUD")
    stqa_max = params.require_float("P-STQA")
    items: list[SceneItem] = []
    for start, end in windows:
        found = source.search(bbox_lonlat, start, end, max_cloud)
        items.extend(
            i for i in found if i.platform.lower().replace("_", "-") in ("landsat-8", "landsat-9")
        )  # Landsat 7 never mixed in
    items.sort(key=lambda i: i.acquired)

    layers: dict[str, list[FloatArray]] = {k: [] for k in ("st", "ndvi", "ndbi", "ndwi", "bsi")}
    records: list[SceneRecord] = []
    nan_layer = np.full(grid.shape, np.nan)
    for item in items:
        scene = _read_scene(item, grid, stqa_max)
        valid_pct = round(100.0 * float(np.isfinite(scene["st"]).mean()), 2)
        if valid_pct == 0.0:
            _log.warning("scene_without_valid_pixels", scene=item.scene_id)
            continue
        for key in layers:
            layers[key].append(scene.get(key, nan_layer))
        records.append(
            SceneRecord(
                item.scene_id, item.acquired.date(), item.platform, item.cloud_cover, valid_pct
            )
        )
        _log.info("scene_read", scene=item.scene_id, valid_pixel_pct=valid_pct)

    def stack(key: str) -> FloatArray:
        return np.stack(layers[key]) if layers[key] else np.empty((0, *grid.shape))

    return SceneStack(
        grid, stack("st"), stack("ndvi"), stack("ndbi"), stack("ndwi"), stack("bsi"), records
    )
