"""M8 Population exposure.

Building-level allocation of a gridded population (WorldPop):
``pop_b = Σ_cells pop_cell · area(b∩cell) / Σ_{b'∈cell} area(b'∩cell)``.

Ward population is the exact (coverage-weighted) zonal sum of the grid, so it
is mass-conserving even where footprints are missing; ``allocation_coverage``
reports how much of it the buildings carry. An official ward figure, when
given, scales by ``k_w = official / modelled`` capped by ``P-POPSCALE-CAP``.

``exposed_pop_w = Σ_b pop_b · 1[heat_local_b ≥ P-TAU]`` where ``heat_local_b``
is the neighbourhood (3×3 pixel) mean ΔLST — never the roof's own temperature.
Wards flagged ``buildings_incomplete`` use the grid instead (labelled).
Vulnerability (age) is ``unavailable`` unless reliable data exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds
from scipy import ndimage

from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.pipeline.grid import FloatArray, Grid, warp_to_grid, zonal_stats

__all__ = ["PopulationResult", "allocate_population", "neighbourhood_mean"]

_log = get_logger("pipeline.m08")


@dataclass
class PopulationResult:
    building_pop: pd.Series  # index building_id
    building_heat_local: pd.Series  # index building_id (°C ΔLST, neighbourhood mean)
    ward_table: pd.DataFrame  # index ward_id
    allocated_total: float
    grid_total_in_building_cells: float
    source: str


def neighbourhood_mean(array: FloatArray, size: int = 3) -> FloatArray:
    """NaN-aware focal mean."""
    valid = np.isfinite(array)
    filled = np.where(valid, array, 0.0)
    total = ndimage.uniform_filter(filled, size=size, mode="nearest")
    count = ndimage.uniform_filter(valid.astype(np.float64), size=size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[count == 0] = np.nan
    return out  # type: ignore[no-any-return]


def _allocate(pop_path: Path, buildings: gpd.GeoDataFrame) -> tuple[pd.Series, float]:
    """Per-building population and the grid total over cells touched by buildings."""
    with rasterio.open(pop_path) as src:
        b_src = buildings.to_crs(src.crs)
        minx, miny, maxx, maxy = b_src.total_bounds
        window = from_bounds(minx, miny, maxx, maxy, src.transform).round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        data = src.read(1, window=window).astype(np.float64)
        if src.nodata is not None:
            data[data == src.nodata] = 0.0
        data[~np.isfinite(data)] = 0.0
        t = src.window_transform(window)
        crs = src.crs

    rows, cols = (idx.ravel() for idx in np.indices(data.shape))
    pops = data.ravel()
    keep = pops > 0  # empty cells contribute nothing
    rows, cols, pops = rows[keep], cols[keep], pops[keep]
    xa, xb = t.c + cols * t.a, t.c + (cols + 1) * t.a
    ya, yb = t.f + rows * t.e, t.f + (rows + 1) * t.e
    cells = gpd.GeoDataFrame(
        {"cell": rows * data.shape[1] + cols, "pop": pops},
        geometry=shapely.box(
            np.minimum(xa, xb), np.minimum(ya, yb), np.maximum(xa, xb), np.maximum(ya, yb)
        ),
        crs=crs,
    )
    pieces = gpd.overlay(
        b_src[["building_id", "geometry"]], cells, how="intersection", keep_geom_type=True
    )
    pieces["a"] = pieces.geometry.area
    pieces["share"] = pieces["a"] / pieces.groupby("cell")["a"].transform("sum")
    pieces["pop_b"] = pieces["pop"] * pieces["share"]
    pop_b = pieces.groupby("building_id")["pop_b"].sum().reindex(buildings.building_id).fillna(0.0)
    grid_total = float(pieces.drop_duplicates("cell")["pop"].sum())
    return pop_b, grid_total


def allocate_population(
    pop_path: Path,
    population_source: str,
    buildings: gpd.GeoDataFrame,
    buildings_incomplete: pd.Series,
    wards_utm: gpd.GeoDataFrame,
    grid: Grid,
    dlst_c: FloatArray,
    params: ParamRegistry,
    official: Mapping[str, float] | None = None,
) -> PopulationResult:
    tau = params.require_float("P-TAU")
    cap = params.require("P-POPSCALE-CAP")

    if buildings.empty:
        pop_b, grid_total = pd.Series(dtype=float), 0.0
    else:
        pop_b, grid_total = _allocate(pop_path, buildings)

    # Ward population: exact zonal sum of the grid (mass-conserving).
    with rasterio.open(pop_path) as src:
        native = Grid(str(src.crs), src.transform, src.width, src.height)
        arr = src.read(1).astype(np.float64)
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
    ward_pop = zonal_stats(native, arr, wards_utm, ["sum"])["sum"].to_numpy()

    table = pd.DataFrame(index=pd.Index(wards_utm.ward_id, name="ward_id"))
    table["population_model"] = ward_pop
    scale = pd.Series(1.0, index=table.index)
    if official:
        for wid, value in official.items():
            if wid in scale.index and table.loc[wid, "population_model"] > 0:
                k = value / table.loc[wid, "population_model"]
                scale[wid] = float(np.clip(k, float(cap["min"]), float(cap["max"])))
    table["scale_factor"] = scale
    table["population"] = table["population_model"] * scale
    area_km2 = wards_utm.geometry.area.to_numpy() / 1e6
    table["density_per_km2"] = table["population"] / area_km2

    ward_of = buildings.set_index("building_id")["ward_id"]
    pop_b = pop_b * ward_of.reindex(pop_b.index).map(scale).fillna(1.0)
    by_ward = pop_b.groupby(ward_of.reindex(pop_b.index)).sum()
    table["allocated_population"] = by_ward.reindex(table.index).fillna(0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        table["allocation_coverage"] = table["allocated_population"] / table["population"]

    # Neighbourhood heat at each building centroid.
    local = neighbourhood_mean(dlst_c, 3)
    cent = buildings.geometry.centroid.to_crs(grid.crs)
    heat_local = pd.Series(
        grid.sample(local, cent.x.to_numpy(), cent.y.to_numpy()),
        index=buildings.building_id.to_numpy(),
    )

    exposed_b = pop_b.where(heat_local.reindex(pop_b.index) >= tau, 0.0)
    building_exposure = exposed_b.groupby(ward_of.reindex(pop_b.index)).sum()

    # Grid-based exposure (for wards with incomplete footprints).
    pop30 = warp_to_grid(str(pop_path), grid, resampling=Resampling.nearest).astype(np.float64)
    pop30[~np.isfinite(pop30) | (pop30 < 0)] = 0.0
    pop30 *= grid.pixel_area_m2 / native.pixel_area_m2
    exposed_px = np.where(local >= tau, pop30, 0.0)
    grid_exposure = zonal_stats(grid, exposed_px, wards_utm, ["sum"])["sum"].to_numpy()

    incomplete = buildings_incomplete.reindex(table.index).fillna(False).astype(bool)
    table["exposed_population"] = np.where(
        incomplete,
        grid_exposure * scale.to_numpy(),
        building_exposure.reindex(table.index).fillna(0.0).to_numpy(),
    )
    table["exposure_method"] = np.where(incomplete, "grid", "buildings")
    _log.info(
        "population_allocated",
        allocated=round(float(pop_b.sum())),
        grid_total_in_building_cells=round(grid_total),
    )
    return PopulationResult(
        pop_b, heat_local, table, float(pop_b.sum()), grid_total, population_source
    )
