"""Loads a city's input datasets from the paths in its city config.

A missing source returns ``None``; modules turn that into ``unavailable`` outputs
(rule 2) rather than failing or substituting defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import geopandas as gpd
import pandas as pd

from packages.core.city import CityConfig

__all__ = ["CityInputs"]


@dataclass
class CityInputs:
    city: CityConfig

    def _path(self, name: str) -> Path | None:
        path = self.city.source(name).resolve()
        return path if path is not None and path.exists() else None

    # ------------------------------------------------------------------ vectors
    @cached_property
    def wards(self) -> gpd.GeoDataFrame | None:
        """Ward polygons with standard columns ``ward_id, name, name_hi`` in EPSG:4326."""
        path = self._path("wards")
        if path is None:
            return None
        ref = self.city.source("wards")
        raw = gpd.read_file(path).to_crs("EPSG:4326")
        out = gpd.GeoDataFrame(
            {
                "ward_id": raw[ref.extra("id_field", "ward_id")].astype(str),
                "name": raw[ref.extra("name_field", "name")].astype(str),
                "name_hi": raw[ref.extra("name_hi_field", "name_hi")].astype(str)
                if ref.extra("name_hi_field", "name_hi") in raw
                else raw[ref.extra("name_field", "name")].astype(str),
            },
            geometry=raw.geometry,
            crs="EPSG:4326",
        )
        return out

    @property
    def boundary_version(self) -> str:
        return str(self.city.source("wards").extra("boundary_version", "unversioned"))

    @cached_property
    def buildings(self) -> gpd.GeoDataFrame | None:
        path = self._path("buildings")
        return gpd.read_parquet(path) if path else None

    @property
    def buildings_dataset_id(self) -> str:
        return str(self.city.source("buildings").extra("dataset_id", "unknown"))

    @cached_property
    def facilities(self) -> gpd.GeoDataFrame | None:
        path = self._path("facilities")
        return gpd.read_file(path).to_crs("EPSG:4326") if path else None

    @cached_property
    def protected_areas(self) -> gpd.GeoDataFrame | None:
        path = self._path("protected_areas")
        return gpd.read_file(path).to_crs("EPSG:4326") if path else None

    @cached_property
    def trend_series(self) -> pd.DataFrame | None:
        path = self._path("trend_series")
        return pd.read_parquet(path) if path else None

    # ------------------------------------------------------------------ rasters / files
    @property
    def population_path(self) -> Path | None:
        return self._path("population")

    @property
    def population_source(self) -> str:
        return str(self.city.source("population").extra("source", "population grid"))

    @property
    def landcover_path(self) -> Path | None:
        return self._path("landcover")

    @property
    def landcover_year(self) -> int | None:
        year = self.city.source("landcover").extra("year")
        return int(year) if year else None

    @property
    def dem_path(self) -> Path | None:
        return self._path("dem")

    @property
    def landsat_items_dir(self) -> Path | None:
        raw = self.city.sources.get("landsat_items")
        if isinstance(raw, str) and raw not in ("planetary_computer", "usgs_s3"):
            path = self.city.source("landsat_items").resolve()
            return path if path and path.exists() else None
        return None

    @property
    def firms_path(self) -> Path | None:
        return self._path("firms")

    @property
    def nwp_path(self) -> Path | None:
        return self._path("nwp")

    @property
    def solar_path(self) -> Path | None:
        return self._path("solar")
