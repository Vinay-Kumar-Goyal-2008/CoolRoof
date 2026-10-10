"""M1+2 Location input and boundary.

Resolves a click, ward id, ward name or polygon into a ``LocationRef``
(ward, city, state, DISCOM, geometry, buffered bbox, centroid, UTM area).
Ward layers are repaired (``make_valid``, sliver removal) once when loaded.
Without ward polygons the city falls back to a 500 m grid (``unit_type: grid``).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
from pydantic import BaseModel
from shapely import make_valid
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from packages.core.city import CityConfig
from packages.core.enums import UnitType
from packages.core.errors import IncompleteError, InputValidationError, NotFoundError

__all__ = ["LocationRef", "WardLayer", "build_ward_layer", "grid_fallback_units"]

SLIVER_M2 = 1.0  # polygon parts smaller than this are geometry noise, not territory
GRID_CELL_M = 500.0


class LocationRef(BaseModel):
    ward_id: str
    ward_name: str
    ward_name_hi: str
    city: str
    state: str
    discom: str
    unit_type: UnitType
    boundary_version: str
    centroid: tuple[float, float]  # lon, lat
    bbox: tuple[float, float, float, float]  # buffered, lon/lat
    area_m2: float
    geometry: dict[str, Any]  # GeoJSON (EPSG:4326)
    point: tuple[float, float] | None = None  # the resolved click, if any


def _normalise_name(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _clean_polygon(geom: BaseGeometry) -> BaseGeometry:
    """``make_valid`` and keep only polygonal parts (drops stray lines/points)."""
    fixed = make_valid(geom)
    if isinstance(fixed, Polygon | MultiPolygon):
        return fixed
    polys = [g for g in getattr(fixed, "geoms", []) if isinstance(g, Polygon | MultiPolygon)]
    return MultiPolygon([p for g in polys for p in getattr(g, "geoms", [g])])


@dataclass
class WardLayer:
    """Validated ward polygons for one city, in both EPSG:4326 and city UTM."""

    city: CityConfig
    wards: gpd.GeoDataFrame  # EPSG:4326: ward_id, name, name_hi, geometry
    wards_utm: gpd.GeoDataFrame
    unit_type: UnitType
    boundary_version: str
    repairs: dict[str, int]

    # ------------------------------------------------------------------ resolution
    def _ref(self, idx: Any, point: tuple[float, float] | None = None) -> LocationRef:
        row = self.wards.loc[idx]
        utm_geom = self.wards_utm.loc[idx].geometry
        buffered = gpd.GeoSeries(
            [utm_geom.buffer(self.city.bbox_buffer_km * 1000)], crs=self.city.utm_crs
        ).to_crs("EPSG:4326")
        centroid = gpd.GeoSeries([utm_geom.centroid], crs=self.city.utm_crs).to_crs("EPSG:4326")[0]
        discom = self.city.discom_for()
        return LocationRef(
            ward_id=row.ward_id,
            ward_name=row["name"],
            ward_name_hi=row["name_hi"],
            city=self.city.slug,
            state=discom.state,
            discom=discom.discom,
            unit_type=self.unit_type,
            boundary_version=self.boundary_version,
            centroid=(round(centroid.x, 6), round(centroid.y, 6)),
            bbox=tuple(round(v, 6) for v in buffered.total_bounds),  # type: ignore[arg-type]
            area_m2=round(float(utm_geom.area), 1),
            geometry=mapping(row.geometry),
            point=point,
        )

    def ward_ids(self) -> list[str]:
        return list(self.wards.ward_id)

    def by_id(self, ward_id: str) -> LocationRef:
        hits = self.wards.index[self.wards.ward_id == ward_id]
        if len(hits) == 0:
            raise NotFoundError(f"ward '{ward_id}' not found in {self.city.slug}")
        return self._ref(hits[0])

    def by_name(self, name: str) -> LocationRef:
        """Exact name match in any script (English or Hindi), case/spacing-insensitive."""
        key = _normalise_name(name)
        for idx, row in self.wards.iterrows():
            names = {
                _normalise_name(row["name"]),
                _normalise_name(row["name_hi"]),
                _normalise_name(row["ward_id"]),
            }
            if key in names:
                return self._ref(idx)
        raise NotFoundError(f"no ward named '{name}' in {self.city.slug}")

    def by_point(self, lon: float, lat: float) -> LocationRef:
        """Point-in-polygon. Outside → 404; inside several (overlap) → ask the user (422)."""
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise InputValidationError("coordinates out of range")
        pt = Point(lon, lat)
        hits = self.wards.index[self.wards.contains(pt)]
        if len(hits) == 0:
            raise NotFoundError("point is outside the city's wards")
        if len(hits) > 1:
            candidates = [self.wards.loc[i].ward_id for i in hits]
            raise IncompleteError(
                "point falls in more than one ward; choose one", details={"candidates": candidates}
            )
        return self._ref(hits[0], point=(lon, lat))

    def by_polygon(self, geojson: dict[str, Any]) -> LocationRef:
        """A user-drawn polygon (e.g. a roof) resolves to the ward containing its centroid."""
        try:
            geom = shape(geojson)
        except (ValueError, AttributeError, KeyError) as exc:
            raise InputValidationError(f"invalid GeoJSON geometry: {exc}") from exc
        if geom.is_empty or not geom.is_valid:
            raise InputValidationError("polygon is empty or invalid")
        c = geom.centroid
        return self.by_point(c.x, c.y)

    def by_address(self, address: str) -> LocationRef:
        """Address geocoding has no verified source in the spec ([NV]); ask for a map click."""
        try:
            return self.by_name(address)
        except NotFoundError:
            raise IncompleteError(
                "address lookup is not available; please click your location on the map",
                details={"next_question": "location_click"},
            ) from None

    # ------------------------------------------------------------------ verify helpers
    def overlap_area_m2(self) -> float:
        utm = self.wards_utm
        total = 0.0
        for i in range(len(utm)):
            for j in range(i + 1, len(utm)):
                total += utm.geometry.iloc[i].intersection(utm.geometry.iloc[j]).area
        return float(total)


def build_ward_layer(
    city: CityConfig, wards: gpd.GeoDataFrame | None, boundary_version: str
) -> WardLayer:
    """Validate a ward layer (or build the grid fallback when ``wards`` is None)."""
    if wards is None or wards.empty:
        units = grid_fallback_units(city)
        return WardLayer(
            city,
            units,
            units.to_crs(city.utm_crs),
            UnitType.GRID,
            f"grid-{int(GRID_CELL_M)}m",
            {"grid_fallback": len(units)},
        )

    gdf = wards.copy()
    repairs = {"made_valid": 0, "slivers_dropped": 0}
    utm = gdf.to_crs(city.utm_crs)
    cleaned = []
    for geom in utm.geometry:
        fixed = geom if geom.is_valid else _clean_polygon(geom)
        repairs["made_valid"] += int(not geom.is_valid)
        parts = list(getattr(fixed, "geoms", [fixed]))
        kept = [p for p in parts if p.area >= SLIVER_M2]
        repairs["slivers_dropped"] += len(parts) - len(kept)
        cleaned.append(kept[0] if len(kept) == 1 else MultiPolygon(kept))
    utm = utm.set_geometry(cleaned)
    gdf = utm.to_crs("EPSG:4326")
    gdf = gdf.reset_index(drop=True)
    if gdf.ward_id.duplicated().any():
        raise InputValidationError("ward layer has duplicate ward ids")
    return WardLayer(city, gdf, gdf.to_crs(city.utm_crs), UnitType.WARD, boundary_version, repairs)


def grid_fallback_units(city: CityConfig) -> gpd.GeoDataFrame:
    """500 m square cells over the city bbox (spec §3 fallback: no ward polygons)."""
    bbox = gpd.GeoSeries([box(*city.bbox)], crs="EPSG:4326").to_crs(city.utm_crs)
    minx, miny, maxx, maxy = bbox.total_bounds
    cells, ids = [], []
    for r, y in enumerate(np.arange(maxy, miny, -GRID_CELL_M)):
        for c, x in enumerate(np.arange(minx, maxx, GRID_CELL_M)):
            cells.append(box(x, y - GRID_CELL_M, x + GRID_CELL_M, y))
            ids.append(f"G{r:03d}_{c:03d}")
    utm = gpd.GeoDataFrame(
        {"ward_id": ids, "name": ids, "name_hi": ids}, geometry=cells, crs=city.utm_crs
    )
    return utm.to_crs("EPSG:4326")
