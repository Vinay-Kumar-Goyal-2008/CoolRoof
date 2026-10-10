"""M7 Building footprints.

Reprojects to UTM, repairs, de-duplicates and drops tiny footprints, assigns
each building to a ward by centroid, and aggregates per ward. ``roof_area`` is
planimetric (flat-equivalent) [ASSUME]. Wards whose footprints cover too little
of the WorldCover built class (relative to the city median) are flagged ``buildings_incomplete`` and their
roof ranking is withheld.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from packages.core.ids import building_id
from packages.core.logging import get_logger
from packages.core.params import ParamRegistry

__all__ = ["BuildingsResult", "process_buildings"]

_log = get_logger("pipeline.m07")
_ID_PRECISION_DEG = 1e-7  # ~1 cm; stabilises ids against float noise in the source


@dataclass
class BuildingsResult:
    buildings: gpd.GeoDataFrame  # UTM; building_id, ward_id, area_m2, confidence, floors, eligible
    ward_table: pd.DataFrame  # index ward_id
    dataset_id: str
    report: dict[str, int] = field(default_factory=dict)


def _largest_polygon(geom: BaseGeometry) -> Polygon | None:
    fixed = geom if geom.is_valid else shapely.make_valid(geom)
    if isinstance(fixed, Polygon):
        return fixed
    parts = [g for g in getattr(fixed, "geoms", []) if isinstance(g, Polygon | MultiPolygon)]
    polys = [p for g in parts for p in getattr(g, "geoms", [g])]
    return max(polys, key=lambda p: p.area) if polys else None


def process_buildings(
    raw: gpd.GeoDataFrame,
    dataset_id: str,
    wards_utm: gpd.GeoDataFrame,
    wc_built_fraction: pd.Series | None,
    params: ParamRegistry,
) -> BuildingsResult:
    """Clean footprints and aggregate them per ward."""
    min_area = params.require_float("P-BLDG-MINAREA")
    min_conf = params.require_float("P-BLDG-CONF")
    incomplete_ratio = params.require_float("P-BLDG-INCOMPLETE")
    report = {"input": len(raw)}

    src = raw.to_crs("EPSG:4326")
    ids = [
        building_id(dataset_id, shapely.set_precision(g, _ID_PRECISION_DEG).wkb)
        for g in src.geometry
    ]
    gdf = src.assign(building_id=ids).to_crs(wards_utm.crs)

    gdf = gdf.drop_duplicates("building_id")
    report["exact_duplicates_removed"] = report["input"] - len(gdf)

    repaired = gdf.geometry.map(_largest_polygon)
    report["repaired"] = int((~gdf.geometry.is_valid).sum())
    gdf = gdf.set_geometry(repaired)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    gdf = gdf.assign(area_m2=gdf.geometry.area)
    small = gdf.area_m2 < min_area
    report["below_min_area"] = int(small.sum())
    gdf = gdf[~small]

    # Near-duplicates (same footprint re-digitised): same centroid at 1 m and area within 1 %.
    key = (
        gdf.geometry.centroid.x.round(0).astype(int).astype(str)
        + "_"
        + gdf.geometry.centroid.y.round(0).astype(int).astype(str)
        + "_"
        + (gdf.area_m2 / 10).round(0).astype(int).astype(str)
    )
    near_dup = key.duplicated()
    report["near_duplicates_removed"] = int(near_dup.sum())
    gdf = gdf[~near_dup]

    centroids = gpd.GeoDataFrame(gdf[["building_id"]], geometry=gdf.geometry.centroid, crs=gdf.crs)
    joined = gpd.sjoin(
        centroids, wards_utm[["ward_id", "geometry"]], predicate="within", how="left"
    )
    gdf = gdf.assign(ward_id=joined["ward_id"].to_numpy())
    report["outside_wards"] = int(gdf.ward_id.isna().sum())
    gdf = gdf[gdf.ward_id.notna()]

    confidence = gdf["confidence"] if "confidence" in gdf else pd.Series(np.nan, index=gdf.index)
    floors = gdf["floors"] if "floors" in gdf else pd.Series(pd.NA, index=gdf.index)
    gdf = gdf.assign(
        confidence=confidence,
        floors=floors.astype("Int64"),
        eligible=(confidence.fillna(0) >= min_conf),
    )
    buildings = gpd.GeoDataFrame(
        gdf[
            ["building_id", "ward_id", "area_m2", "confidence", "floors", "eligible", "geometry"]
        ].reset_index(drop=True),
        geometry="geometry",
        crs=wards_utm.crs,
    )

    ward_area = pd.Series(wards_utm.geometry.area.to_numpy(), index=wards_utm.ward_id)
    grouped = buildings.groupby("ward_id")
    table = pd.DataFrame(index=pd.Index(wards_utm.ward_id, name="ward_id"))
    table["building_count"] = grouped.size().reindex(table.index).fillna(0).astype(int)
    table["roof_area_m2"] = grouped.area_m2.sum().reindex(table.index).fillna(0.0)
    table["eligible_roof_area_m2"] = (
        buildings[buildings.eligible]
        .groupby("ward_id")
        .area_m2.sum()
        .reindex(table.index)
        .fillna(0.0)
    )
    table["built_fraction"] = table["roof_area_m2"] / ward_area
    table["density_per_km2"] = table["building_count"] / (ward_area / 1e6)
    if wc_built_fraction is not None:
        ratio = table["built_fraction"] / wc_built_fraction.reindex(table.index)
        table["footprint_vs_worldcover"] = ratio
        # Relative to the city median: footprint datasets under-cover whole cities
        # evenly, so only wards far below the city's own coverage are flagged.
        table["buildings_incomplete"] = ratio < incomplete_ratio * ratio.median()
    else:
        table["footprint_vs_worldcover"] = np.nan
        table["buildings_incomplete"] = False
    report["output"] = len(buildings)
    _log.info("buildings_processed", **report)
    return BuildingsResult(buildings, table, dataset_id, report)
