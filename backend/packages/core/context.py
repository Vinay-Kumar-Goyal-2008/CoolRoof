"""Ward Context and Roof Context models (§4.2) — the central data contract.

Every field is a :class:`ValueEnvelope`. Sections only accept the field names
listed in the spec, so no module can invent a field. Downstream modules and the
agent read contexts, never raw datasets.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.core.enums import UnitType, ValueClass
from packages.core.envelope import ValueEnvelope

__all__ = [
    "CONTEXT_FIELDS",
    "DataQuality",
    "LocationSection",
    "RoofContext",
    "WardContext",
    "context_json_schema",
    "count_classes",
]

CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "heat": (
        "mean_dlst_c",
        "p90_lst_c",
        "persistence",
        "z_vs_city",
        "n_obs",
        "heat_type",
        "top_drivers",
        "drivers_ref",
        "heatdome_risk",
        "heatdome_ref",
    ),
    "built_environment": (
        "building_count",
        "roof_area_m2",
        "built_fraction",
        "eligible_roof_area_m2",
    ),
    "population": ("population", "density", "exposed_population"),
    "environment": (
        "ndvi_mean",
        "water_distance_m",
        "elevation_mean_m",
        "ndvi_trend_slope",
        "bsi_trend_slope",
        "lst_trend_slope",
        "degradation_signal",
        "bare_fraction",
        "soc_mean",
    ),
    "infrastructure": (
        "hospital_count",
        "school_count",
        "cooling_point_count",
        "nearest_hospital_m",
        "facilities_per_10k_exposed",
    ),
    "solar": ("specific_yield", "rooftop_potential_kwp_est"),
    "hazards": (
        "fire_events_30d",
        "fire_incidents_30d",
        "protected_area_overlap",
        "nearest_protected_area_m",
        "habitat_pressure_max",
    ),
    "administrative": ("discom", "policy_ref"),
}

Section = dict[str, ValueEnvelope]


class LocationSection(BaseModel):
    city: str
    state: str
    centroid: tuple[float, float]
    area_km2: float
    unit_type: UnitType
    name: str
    name_hi: str


class DataQuality(BaseModel):
    available: int = 0
    unavailable: int = 0
    estimated: int = 0
    stale: int = 0
    context_confidence: float = Field(ge=0.0, le=1.0)
    flags: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


def _check_section(name: str, value: Section) -> Section:
    allowed = set(CONTEXT_FIELDS[name])
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{name}: fields not in the spec schema: {sorted(unknown)}")
    return value


class WardContext(BaseModel):
    """Provenance-tagged record for one ward. Only M8.5 writes whole versions."""

    model_config = ConfigDict(extra="forbid")

    ward_id: str
    boundary_version: str
    context_version: str
    run_id: str
    location: LocationSection
    heat: Section = Field(default_factory=dict)
    built_environment: Section = Field(default_factory=dict)
    population: Section = Field(default_factory=dict)
    environment: Section = Field(default_factory=dict)
    infrastructure: Section = Field(default_factory=dict)
    solar: Section = Field(default_factory=dict)
    hazards: Section = Field(default_factory=dict)
    administrative: Section = Field(default_factory=dict)
    data_quality: DataQuality

    @field_validator(*CONTEXT_FIELDS.keys())
    @classmethod
    def _sections_use_spec_fields(cls, value: Section, info: Any) -> Section:
        return _check_section(info.field_name, value)

    def field(self, path: str) -> ValueEnvelope:
        """Envelope at ``section.field``; an absent field reads as ``unavailable``."""
        section, _, name = path.partition(".")
        env = getattr(self, section).get(name)
        if env is None:
            return ValueEnvelope.unavailable("ward_context", f"{path} not computed")
        return env  # type: ignore[no-any-return]

    def value(self, path: str) -> Any:
        """The raw value at ``section.field`` or ``None`` when unavailable."""
        env = self.field(path)
        return env.value if env.is_available else None

    def iter_envelopes(self) -> list[tuple[str, ValueEnvelope]]:
        out: list[tuple[str, ValueEnvelope]] = []
        for section in CONTEXT_FIELDS:
            for name, env in getattr(self, section).items():
                out.append((f"{section}.{name}", env))
        return out

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class RoofContext(BaseModel):
    """Per-building record (§4.2): geometry, area, local heat, people, solar, intervention."""

    model_config = ConfigDict(extra="forbid")

    building_id: str
    ward_id: str
    city: str
    context_version: str
    geometry: dict[str, Any]
    area: ValueEnvelope
    local_heat: ValueEnvelope
    pop_b: ValueEnvelope
    floors_est: ValueEnvelope | None = None
    eligible: bool
    solar: dict[str, ValueEnvelope] = Field(default_factory=dict)  # yield, kWp_max
    intervention: dict[str, Any] = Field(default_factory=dict)  # cost, benefit (ranges)
    policy_ref: str | None = None
    ward_ref: str

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def context_json_schema() -> dict[str, Any]:
    """JSON Schema used by the CI schema-validation gate."""
    return WardContext.model_json_schema(by_alias=True)


def count_classes(envelopes: list[ValueEnvelope]) -> dict[str, int]:
    counts = {"available": 0, "unavailable": 0, "estimated": 0, "stale": 0}
    for env in envelopes:
        if env.cls is ValueClass.UNAVAILABLE:
            counts["unavailable"] += 1
        else:
            counts["available"] += 1
            if env.cls is ValueClass.ESTIMATED:
                counts["estimated"] += 1
            if env.cls is ValueClass.STALE:
                counts["stale"] += 1
    return counts
