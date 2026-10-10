"""M8.5 Ward Context Builder (central).

Merges every feature table into one provenance-tagged ``WardContext`` per ward
(and ``RoofContext`` per building) so no downstream module or the agent reads
raw datasets.

Feature tables are registered declaratively (``FeatureTable`` + ``FieldSpec``):
adding a module's output to the context means adding specs, not code paths.
A missing table yields ``unavailable`` envelopes with a reason — never 0.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

from packages.core.context import (
    CONTEXT_FIELDS,
    DataQuality,
    LocationSection,
    RoofContext,
    WardContext,
    count_classes,
)
from packages.core.enums import ValueClass
from packages.core.envelope import ValueEnvelope
from packages.core.params import ParamRegistry
from packages.pipeline.m01_location import WardLayer

__all__ = [
    "ALL_FIELD_SPECS",
    "BASE_FIELD_SPECS",
    "FeatureTable",
    "FieldSpec",
    "build_roof_contexts",
    "build_ward_contexts",
    "flip_stale",
]


@dataclass(frozen=True)
class FeatureTable:
    """A per-ward table produced by some module, with its provenance."""

    name: str
    frame: pd.DataFrame | None  # index: ward_id; None = dataset not provided
    source: str
    value_class: ValueClass = ValueClass.DERIVED
    observed: str | None = None
    resolution_m: float | None = None
    confidence_column: str | None = None
    assumptions: tuple[str, ...] = ()
    missing_reason: str = "dataset not provided"


@dataclass(frozen=True)
class FieldSpec:
    """Maps ``table.column`` to a context path ``section.field``."""

    path: str
    table: str
    column: str
    digits: int | None = 3
    alt: tuple[str, str] | None = None  # (table, column) of a lower-precedence source

    def __post_init__(self) -> None:
        section, _, name = self.path.partition(".")
        if name not in CONTEXT_FIELDS.get(section, ()):
            raise ValueError(f"{self.path} is not a spec context field")


BASE_FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("heat.mean_dlst_c", "heat", "mean_dlst_c", 2),
    FieldSpec("heat.p90_lst_c", "heat", "p90_lst_c", 2),
    FieldSpec("heat.persistence", "heat", "persistence", 3),
    FieldSpec("heat.z_vs_city", "heat", "heat_z", 3),
    FieldSpec("heat.n_obs", "heat", "n_obs", 0),
    FieldSpec("built_environment.building_count", "buildings", "building_count", 0),
    FieldSpec("built_environment.roof_area_m2", "buildings", "roof_area_m2", 0),
    # Precedence: WorldCover built share (10 m, complete) over footprint coverage, which is
    # patchy in informal areas; the footprint share is kept as alt_value.
    FieldSpec(
        "built_environment.built_fraction",
        "landcover",
        "wc_built_fraction",
        3,
        alt=("buildings", "built_fraction"),
    ),
    FieldSpec("built_environment.eligible_roof_area_m2", "buildings", "eligible_roof_area_m2", 0),
    FieldSpec("population.population", "population", "population", 0),
    FieldSpec("population.density", "population", "density_per_km2", 0),
    FieldSpec("population.exposed_population", "population", "exposed_population", 0),
    FieldSpec("environment.ndvi_mean", "heat", "ndvi_mean", 3),
    FieldSpec("environment.water_distance_m", "landcover", "water_distance_m", 0),
    FieldSpec("environment.elevation_mean_m", "dem", "elevation_mean_m", 1),
    FieldSpec("environment.bare_fraction", "landcover", "bare_fraction", 3),
)


EXTRA_FIELD_SPECS: tuple[FieldSpec, ...] = (
    # M20 facilities
    FieldSpec("infrastructure.hospital_count", "infrastructure", "hospital_count", 0),
    FieldSpec("infrastructure.school_count", "infrastructure", "school_count", 0),
    FieldSpec("infrastructure.cooling_point_count", "infrastructure", "cooling_point_count", 0),
    FieldSpec("infrastructure.nearest_hospital_m", "infrastructure", "nearest_hospital_m", 0),
    FieldSpec(
        "infrastructure.facilities_per_10k_exposed",
        "infrastructure",
        "facilities_per_10k_exposed",
        2,
    ),
    # M24 trends
    FieldSpec("environment.ndvi_trend_slope", "trend", "ndvi_trend_slope", 4),
    FieldSpec("environment.bsi_trend_slope", "trend", "bsi_trend_slope", 4),
    FieldSpec("environment.lst_trend_slope", "trend", "lst_trend_slope", 3),
    FieldSpec("environment.degradation_signal", "trend", "degradation_signal", None),
    # M22 + M23 hazards
    FieldSpec("hazards.fire_events_30d", "hazard", "fire_events_30d", 0),
    FieldSpec("hazards.protected_area_overlap", "hazard", "protected_area_overlap", 3),
    FieldSpec("hazards.nearest_protected_area_m", "hazard", "nearest_protected_area_m", 0),
    FieldSpec("hazards.habitat_pressure_max", "hazard", "habitat_pressure_max", None),
)
ALL_FIELD_SPECS: tuple[FieldSpec, ...] = (*BASE_FIELD_SPECS, *EXTRA_FIELD_SPECS)


def _clean(value: Any, digits: int | None) -> Any:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy scalar → plain Python
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return round(float(value), digits) if digits else round(float(value))
    return value


@dataclass
class _Builder:
    tables: Mapping[str, FeatureTable]
    processed: str
    stale_after: str

    def envelope(self, spec: FieldSpec, ward_id: str) -> ValueEnvelope:
        table = self.tables.get(spec.table)
        if table is None or table.frame is None:
            reason = table.missing_reason if table else f"{spec.table} not computed"
            source = table.source if table else spec.table
            return ValueEnvelope.unavailable(source, reason)
        frame = table.frame
        raw = (
            frame.at[ward_id, spec.column]
            if (ward_id in frame.index and spec.column in frame.columns)
            else None
        )
        value = _clean(raw, spec.digits)
        if value is None:
            return ValueEnvelope.unavailable(table.source, f"no valid {spec.column} for ward")
        confidence = None
        if table.confidence_column and table.confidence_column in frame.columns:
            confidence = _clean(frame.at[ward_id, table.confidence_column], 3)
        alt = None
        if spec.alt:
            alt_table = self.tables.get(spec.alt[0])
            if (
                alt_table is not None
                and alt_table.frame is not None
                and spec.alt[1] in alt_table.frame.columns
                and ward_id in alt_table.frame.index
            ):
                alt = _clean(alt_table.frame.at[ward_id, spec.alt[1]], spec.digits)
        return ValueEnvelope.of(
            value,
            table.value_class,
            table.source,
            observed=table.observed,
            processed=self.processed,
            resolution_m=table.resolution_m,
            confidence=confidence,
            stale_after=self.stale_after,
            assumptions=table.assumptions,
            alt_value=alt,
        )

    def fallback(self, spec: FieldSpec, ward_id: str) -> ValueEnvelope | None:
        """Lower-precedence source when the primary is missing (labelled estimated)."""
        if not spec.alt:
            return None
        alt_table = self.tables.get(spec.alt[0])
        if alt_table is None or alt_table.frame is None:
            return None
        frame = alt_table.frame
        if ward_id not in frame.index or spec.alt[1] not in frame.columns:
            return None
        value = _clean(frame.at[ward_id, spec.alt[1]], spec.digits)
        if value is None:
            return None
        return ValueEnvelope.of(
            value,
            ValueClass.ESTIMATED,
            alt_table.source,
            observed=alt_table.observed,
            processed=self.processed,
            resolution_m=alt_table.resolution_m,
            stale_after=self.stale_after,
        )


def _data_quality(
    sections: dict[str, dict[str, ValueEnvelope]], critical: Sequence[str], flags: list[str]
) -> DataQuality:
    envelopes = [env for sec in sections.values() for env in sec.values()]
    counts = count_classes(envelopes)
    available_conf: list[float] = []
    missing: list[str] = []
    n_available = 0
    for path in critical:
        section, _, name = path.partition(".")
        env = sections.get(section, {}).get(name)
        if env is None or not env.is_available:
            missing.append(path)
            continue
        n_available += 1
        if env.confidence is not None:
            available_conf.append(env.confidence)
    share = n_available / len(critical) if critical else 1.0
    confidence = round(share * (min(available_conf) if available_conf else 1.0), 3)
    return DataQuality(**counts, context_confidence=confidence, flags=flags, missing=missing)


def build_ward_contexts(
    wards: WardLayer,
    tables: Iterable[FeatureTable],
    specs: Sequence[FieldSpec],
    params: ParamRegistry,
    *,
    context_version: str,
    run_id: str,
    run_date: date,
    flags: Mapping[str, list[str]] | None = None,
    administrative: Mapping[str, Mapping[str, ValueEnvelope]] | None = None,
    extras: Mapping[str, Mapping[str, ValueEnvelope]] | None = None,
) -> list[WardContext]:
    """One ``WardContext`` per ward from the registered feature tables."""
    stale_after = (run_date + timedelta(days=int(params.require("P-STALE-CONTEXT")))).isoformat()
    builder = _Builder({t.name: t for t in tables}, run_date.isoformat(), stale_after)
    critical = list(params.require("P-CTX-CRITICAL"))
    out: list[WardContext] = []
    discom = wards.city.discom_for()
    for idx, row in wards.wards.iterrows():
        ward_id = str(row.ward_id)
        utm_geom = wards.wards_utm.loc[idx].geometry
        centroid = gpd.GeoSeries([utm_geom.centroid], crs=wards.wards_utm.crs).to_crs(4326)[0]
        sections: dict[str, dict[str, ValueEnvelope]] = {s: {} for s in CONTEXT_FIELDS}
        for spec in specs:
            env = builder.envelope(spec, ward_id)
            if not env.is_available:
                env = builder.fallback(spec, ward_id) or env
            section, _, name = spec.path.partition(".")
            sections[section][name] = env
        sections["administrative"]["discom"] = ValueEnvelope.of(
            discom.discom, ValueClass.POLICY, f"city_config:{wards.city.slug}:discom_map"
        )
        for path_section, extra in (administrative or {}).get(ward_id, {}).items():
            sections["administrative"][path_section] = extra
        # Non-tabular values (e.g. a driver list): ward_id → {"section.field": envelope}
        for path, extra_env in (extras or {}).get(ward_id, {}).items():
            section, _, name = path.partition(".")
            if name not in CONTEXT_FIELDS.get(section, ()):
                raise ValueError(f"{path} is not a spec context field")
            sections[section][name] = extra_env
        ward_flags = list((flags or {}).get(ward_id, []))
        out.append(
            WardContext(
                ward_id=ward_id,
                boundary_version=wards.boundary_version,
                context_version=context_version,
                run_id=run_id,
                location=LocationSection(
                    city=wards.city.slug,
                    state=discom.state,
                    centroid=(round(centroid.x, 6), round(centroid.y, 6)),
                    area_km2=round(utm_geom.area / 1e6, 4),
                    unit_type=wards.unit_type,
                    name=str(row["name"]),
                    name_hi=str(row["name_hi"]),
                ),
                data_quality=_data_quality(sections, critical, ward_flags),
                **{s: dict(env.items()) for s, env in sections.items() if env},
            )
        )
    return out


def flip_stale(context: WardContext, today: date) -> WardContext:
    """Staleness job: fields past ``stale_after`` become ``stale`` (values kept)."""
    changed = False
    sections: dict[str, dict[str, ValueEnvelope]] = {}
    for section in CONTEXT_FIELDS:
        current: dict[str, ValueEnvelope] = getattr(context, section)
        updated = {}
        for name, env in current.items():
            if (
                env.is_usable_fresh
                and env.stale_after
                and date.fromisoformat(env.stale_after) <= today
            ):
                updated[name] = env.mark_stale()
                changed = True
            else:
                updated[name] = env
        sections[section] = updated
    if not changed:
        return context
    envelopes = [e for sec in sections.values() for e in sec.values()]
    counts = count_classes(envelopes)
    quality = context.data_quality.model_copy(update=counts)
    return context.model_copy(update={**sections, "data_quality": quality})


def build_roof_contexts(
    buildings: gpd.GeoDataFrame,
    pop_b: pd.Series,
    heat_local: pd.Series,
    *,
    city: str,
    context_version: str,
    buildings_source: str,
    population_source: str,
    heat_source: str,
    incomplete_wards: set[str],
    run_date: date,
    intervention: Mapping[str, dict[str, Any]] | None = None,
) -> list[RoofContext]:
    """One ``RoofContext`` per building. Wards with incomplete footprints are withheld."""
    processed = run_date.isoformat()
    geo = buildings.to_crs("EPSG:4326")
    out: list[RoofContext] = []
    for row, geom in zip(buildings.itertuples(index=False), geo.geometry, strict=True):
        bid = str(row.building_id)
        ward = str(row.ward_id)
        heat = heat_local.get(bid)
        floors = row.floors
        out.append(
            RoofContext(
                building_id=bid,
                ward_id=ward,
                city=city,
                context_version=context_version,
                geometry=mapping(geom),
                area=ValueEnvelope.of(
                    round(float(row.area_m2), 1),
                    ValueClass.DERIVED,
                    buildings_source,
                    processed=processed,
                    assumptions=("planimetric_roof_area",),
                ),
                local_heat=(
                    ValueEnvelope.of(
                        round(float(heat), 2),
                        ValueClass.DERIVED,
                        heat_source,
                        processed=processed,
                        resolution_m=90.0,
                    )
                    if heat is not None and math.isfinite(heat)
                    else ValueEnvelope.unavailable(heat_source, "no valid neighbourhood pixels")
                ),
                pop_b=ValueEnvelope.of(
                    round(float(pop_b.get(bid, 0.0)), 2),
                    ValueClass.ESTIMATED,
                    population_source,
                    processed=processed,
                ),
                floors_est=(
                    ValueEnvelope.of(int(floors), ValueClass.MEASURED, buildings_source)
                    if floors is not None and not pd.isna(floors)
                    else None
                ),
                eligible=bool(row.eligible) and ward not in incomplete_wards,
                intervention=dict((intervention or {}).get(bid, {})),
                ward_ref=f"{city}#{ward}",
            )
        )
    return out
