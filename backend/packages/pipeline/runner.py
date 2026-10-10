"""Batch heat pipeline orchestrator (local stand-in for the Step Functions state machine).

Steps run in spec order; each step's result is kept on the ``PipelineRun`` so
tests, the CLI and the persistence layer share one code path. A missing input
dataset skips its step and the context shows ``unavailable`` for its fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from rasterio.enums import Resampling

from packages.adapters.landsat_source import (
    FixtureLandsatSource,
    LandsatSource,
    PlanetaryComputerSource,
    USGSS3Source,
)
from packages.core.city import CityConfig
from packages.core.context import RoofContext, WardContext
from packages.core.enums import Runtime, ValueClass
from packages.core.ids import context_version, new_run_id
from packages.core.logging import bind_context, get_logger
from packages.core.params import ParamRegistry
from packages.core.settings import AppSettings
from packages.core.timeutil import today as utc_today
from packages.pipeline.grid import FloatArray, Grid, warp_to_grid
from packages.pipeline.inputs import CityInputs
from packages.pipeline.m01_location import WardLayer, build_ward_layer
from packages.pipeline.m03_landsat import SceneStack, preprocess, season_windows
from packages.pipeline.m05_lst import LSTResult, compute_lst
from packages.pipeline.m06_heat import HeatFeatures, compute_heat
from packages.pipeline.m07_buildings import BuildingsResult, process_buildings
from packages.pipeline.m08_population import PopulationResult, allocate_population
from packages.pipeline.m085_context import (
    BASE_FIELD_SPECS,
    FeatureTable,
    build_roof_contexts,
    build_ward_contexts,
)
from packages.pipeline.m09_priority import PriorityResult, score_wards
from packages.pipeline.m11_coolroof import RoofAssessment, assess_roofs

__all__ = ["HeatPipeline", "PipelineRun", "landsat_source_for"]

_log = get_logger("pipeline")


def landsat_source_for(settings: AppSettings, inputs: CityInputs) -> LandsatSource:
    """Fixture items when the city has them, else Planetary Computer (local) / USGS S3 (aws)."""
    if inputs.landsat_items_dir is not None:
        return FixtureLandsatSource(inputs.landsat_items_dir)
    if settings.runtime is Runtime.AWS:
        return USGSS3Source()
    return PlanetaryComputerSource()


@dataclass
class PipelineRun:
    """Everything one pipeline execution produced."""

    city: CityConfig
    params: ParamRegistry
    inputs: CityInputs
    run_id: str
    run_date: date
    wards: WardLayer | None = None
    grid: Grid | None = None
    landcover: NDArray[np.int64] | None = None
    dem: FloatArray | None = None
    stack: SceneStack | None = None
    lst: LSTResult | None = None
    heat: HeatFeatures | None = None
    buildings: BuildingsResult | None = None
    population: PopulationResult | None = None
    contexts: list[WardContext] = field(default_factory=list)
    priority: PriorityResult | None = None
    roof_assessments: list[RoofAssessment] = field(default_factory=list)
    roof_contexts: list[RoofContext] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def context_version(self) -> str:
        return context_version(self.run_date)

    @property
    def incomplete_wards(self) -> set[str]:
        if self.buildings is None:
            return set(self.require(self.wards, "M1+2").ward_ids())
        table = self.buildings.ward_table
        return set(table.index[table["buildings_incomplete"]])

    def require[T](self, value: T | None, name: str) -> T:
        if value is None:
            raise RuntimeError(f"pipeline step '{name}' has not run")
        return value


class HeatPipeline:
    """M1+2 → M3+4 → M5 → M6 → M7 → M8 → M8.5 → M9 → M10–13."""

    def __init__(
        self,
        city: CityConfig,
        params: ParamRegistry,
        landsat: LandsatSource,
        *,
        run_date: date | None = None,
        run_id: str | None = None,
    ) -> None:
        self.run = PipelineRun(
            city=city,
            params=city.apply_overrides(params),
            inputs=CityInputs(city),
            run_id=run_id or new_run_id(city.slug),
            run_date=run_date or utc_today(),
        )
        self._landsat = landsat

    # ------------------------------------------------------------------ M1–M6
    def locate(self) -> WardLayer:
        r = self.run
        r.wards = build_ward_layer(r.city, r.inputs.wards, r.inputs.boundary_version)
        r.grid = Grid.from_bbox_lonlat(r.city.bbox, r.city.utm_crs, buffer_km=r.city.bbox_buffer_km)
        if r.inputs.landcover_path:
            r.landcover = warp_to_grid(
                str(r.inputs.landcover_path), r.grid, resampling=Resampling.nearest
            ).astype(np.int64)
        if r.inputs.dem_path:
            r.dem = warp_to_grid(str(r.inputs.dem_path), r.grid).astype(np.float64)
        r.steps.append("M1+2")
        return r.wards

    def acquire(self) -> SceneStack:
        r = self.run
        windows = season_windows(r.params, r.run_date, r.city.season.years)
        r.stack = preprocess(
            self._landsat, r.require(r.grid, "M1+2"), r.city.bbox, windows, r.params
        )
        r.steps.append("M3+4")
        return r.stack

    def surface_temperature(self) -> LSTResult:
        r = self.run
        grid = r.require(r.grid, "M1+2")
        city_mask = grid.rasterize_ids(r.require(r.wards, "M1+2").wards_utm) >= 0
        r.lst = compute_lst(r.require(r.stack, "M3+4"), r.params, city_mask)
        r.steps.append("M5")
        return r.lst

    def heat_analysis(self) -> HeatFeatures:
        r = self.run
        r.heat = compute_heat(
            r.require(r.stack, "M3+4"),
            r.require(r.lst, "M5"),
            r.require(r.wards, "M1+2").wards_utm,
            r.landcover,
            r.dem,
            r.params,
        )
        r.steps.append("M6")
        return r.heat

    # ------------------------------------------------------------------ M7, M8
    def building_footprints(self) -> BuildingsResult | None:
        r = self.run
        raw = r.inputs.buildings
        if raw is None:
            _log.warning("buildings_unavailable")
            return None
        heat = r.require(r.heat, "M6")
        wc = heat.table.get("wc_built_fraction", None)
        r.buildings = process_buildings(
            raw, r.inputs.buildings_dataset_id, r.require(r.wards, "M1+2").wards_utm, wc, r.params
        )
        r.steps.append("M7")
        return r.buildings

    def population_exposure(self) -> PopulationResult | None:
        r = self.run
        if r.inputs.population_path is None:
            _log.warning("population_unavailable")
            return None
        wards = r.require(r.wards, "M1+2")
        if r.buildings is not None:
            buildings = r.buildings.buildings
            incomplete = r.buildings.ward_table["buildings_incomplete"]
        else:
            buildings = gpd.GeoDataFrame(
                {"building_id": [], "ward_id": []}, geometry=[], crs=wards.wards_utm.crs
            )
            incomplete = pd.Series(True, index=wards.ward_ids())
        r.population = allocate_population(
            r.inputs.population_path,
            r.inputs.population_source,
            buildings,
            incomplete,
            wards.wards_utm,
            r.require(r.grid, "M1+2"),
            r.require(r.heat, "M6").dlst_c,
            r.params,
        )
        r.steps.append("M8")
        return r.population

    # ------------------------------------------------------------------ M8.5
    def feature_tables(self) -> list[FeatureTable]:
        r = self.run
        heat = r.require(r.heat, "M6")
        stack = r.require(r.stack, "M3+4")
        dates = sorted(s.acquired for s in stack.scenes)
        min_obs = r.params.require_float("P-MINOBS")
        heat_frame = heat.table.assign(
            heat_confidence=(heat.table["n_obs"] / (2 * min_obs)).clip(0, 1)
        )
        tables = [
            FeatureTable(
                "heat",
                heat_frame,
                source=(
                    f"landsat_c2l2_st; scenes={len(dates)}; "
                    f"years={dates[0].year}-{dates[-1].year}; reference={heat.reference.method}"
                ),
                observed=f"{dates[0]:%Y-%m}..{dates[-1]:%Y-%m}",
                resolution_m=30.0,
                confidence_column="heat_confidence",
                assumptions=("P-STQA", "P-REF-RING"),
            ),
            FeatureTable(
                "landcover",
                heat.table if r.landcover is not None else None,
                source=f"esa_worldcover_{r.inputs.landcover_year or 'unknown'}",
                resolution_m=10.0,
            ),
            FeatureTable(
                "dem",
                heat.table if r.dem is not None else None,
                source="copernicus_dem_glo30",
                resolution_m=30.0,
            ),
        ]
        if r.buildings is not None:
            conf = r.buildings.buildings.groupby("ward_id")["confidence"].mean()
            frame = r.buildings.ward_table.assign(footprint_confidence=conf)
            tables.append(
                FeatureTable(
                    "buildings",
                    frame,
                    source=f"buildings:{r.buildings.dataset_id}",
                    confidence_column="footprint_confidence",
                )
            )
        else:
            tables.append(FeatureTable("buildings", None, source=r.inputs.buildings_dataset_id))
        tables.append(
            FeatureTable(
                "population",
                r.population.ward_table if r.population else None,
                source=r.inputs.population_source,
                value_class=ValueClass.ESTIMATED,
                assumptions=("P-TAU",),
            )
        )
        return tables

    def ward_flags(self) -> dict[str, list[str]]:
        r = self.run
        heat = r.require(r.heat, "M6").table
        flags: dict[str, list[str]] = {w: [] for w in heat.index}
        for ward in heat.index:
            if bool(heat.at[ward, "low_confidence"]):
                flags[ward].append("low_confidence")
            if bool(heat.at[ward, "ward_too_small"]):
                flags[ward].append("ward_too_small")
        for ward in self.run.incomplete_wards:
            flags.setdefault(ward, []).append("buildings_incomplete")
        if r.population is not None:
            grid_based = r.population.ward_table["exposure_method"] == "grid"
            for ward in r.population.ward_table.index[grid_based]:
                flags[ward].append("exposure_from_grid")
        if r.heat and r.heat.reference.method != "rural_ring":
            for ward in flags:
                flags[ward].append("reference_city_percentile_baseline")
        return flags

    def build_contexts(self) -> list[WardContext]:
        r = self.run
        r.contexts = build_ward_contexts(
            r.require(r.wards, "M1+2"),
            self.feature_tables(),
            BASE_FIELD_SPECS,
            r.params,
            context_version=r.context_version,
            run_id=r.run_id,
            run_date=r.run_date,
            flags=self.ward_flags(),
        )
        r.steps.append("M8.5")
        return r.contexts

    # ------------------------------------------------------------------ M9–M13
    def prioritise(self) -> PriorityResult:
        r = self.run
        r.priority = score_wards(r.contexts, r.params)
        r.steps.append("M9")
        return r.priority

    def assess_roofs(self) -> list[RoofAssessment]:
        r = self.run
        if r.buildings is None or r.population is None:
            return []
        b = r.buildings.buildings
        frame = pd.DataFrame(
            {
                "building_id": b.building_id.to_numpy(),
                "ward_id": b.ward_id.to_numpy(),
                "area_m2": b.area_m2.to_numpy(),
                "pop_b": r.population.building_pop.reindex(b.building_id).fillna(0.0).to_numpy(),
                "heat_local_c": r.population.building_heat_local.reindex(b.building_id).to_numpy(
                    dtype=float
                ),
                "floors": b.floors.to_numpy(),
                "eligible": (b.eligible & ~b.ward_id.isin(r.incomplete_wards)).to_numpy(),
            }
        )
        r.roof_assessments = assess_roofs(frame, r.require(r.grid, "M1+2").pixel_area_m2, r.params)
        r.roof_contexts = build_roof_contexts(
            b,
            r.population.building_pop,
            r.population.building_heat_local,
            city=r.city.slug,
            context_version=r.context_version,
            buildings_source=f"buildings:{r.buildings.dataset_id}",
            population_source=r.population.source,
            heat_source="landsat_c2l2_st; neighbourhood 3x3 mean ΔLST",
            incomplete_wards=r.incomplete_wards,
            run_date=r.run_date,
            intervention={a.building_id: a.to_dict() for a in r.roof_assessments},
        )
        r.steps.append("M10-13")
        return r.roof_assessments

    def run_all(self) -> PipelineRun:
        bind_context(run_id=self.run.run_id)
        self.locate()
        self.acquire()
        self.surface_temperature()
        self.heat_analysis()
        self.building_footprints()
        self.population_exposure()
        self.build_contexts()
        self.prioritise()
        self.assess_roofs()
        _log.info("pipeline_complete", steps=self.run.steps)
        return self.run
