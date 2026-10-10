"""Per-city configuration (``config/cities/<slug>.yaml``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from packages.core.errors import NotFoundError
from packages.core.params import ParamRegistry
from packages.core.settings import BACKEND_ROOT

__all__ = ["CityConfig", "DiscomRef", "SourceRef", "load_city"]


class DiscomRef(BaseModel):
    state: str
    discom: str


class SourceRef(BaseModel):
    """A dataset reference; ``path`` is relative to the backend root."""

    model_config = ConfigDict(extra="allow")

    path: str | None = None
    status: str | None = None

    def resolve(self) -> Path | None:
        return (BACKEND_ROOT / self.path).resolve() if self.path else None

    def extra(self, key: str, default: Any = None) -> Any:
        return (self.model_extra or {}).get(key, default)


class Season(BaseModel):
    start_mmdd: str
    end_mmdd: str
    years: list[int] | int


class CityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: dict[str, str]
    synthetic: bool = False
    state: str
    bbox: tuple[float, float, float, float]
    bbox_buffer_km: float = 2.0
    utm_epsg: int
    season: Season
    discom_map: dict[str, DiscomRef]
    sources: dict[str, SourceRef | str]
    weight_profile: str = "default"
    param_overrides: dict[str, Any] = Field(default_factory=dict)

    @property
    def utm_crs(self) -> str:
        return f"EPSG:{self.utm_epsg}"

    def source(self, name: str) -> SourceRef:
        ref = self.sources.get(name)
        if isinstance(ref, SourceRef):
            return ref
        return SourceRef(path=ref) if ref else SourceRef(status="missing")

    def discom_for(self, area: str = "default") -> DiscomRef:
        return self.discom_map.get(area) or self.discom_map["default"]

    def apply_overrides(self, params: ParamRegistry) -> ParamRegistry:
        return params.with_overrides(self.param_overrides) if self.param_overrides else params


@lru_cache(maxsize=16)
def load_city(slug: str, config_dir: Path | None = None) -> CityConfig:
    """Load ``config/cities/<slug>.yaml``; 404 when the city is not configured."""
    folder = config_dir or BACKEND_ROOT / "config"
    path = folder / "cities" / f"{slug}.yaml"
    if not path.is_file():
        raise NotFoundError(f"city '{slug}' is not configured")
    with path.open(encoding="utf-8") as fh:
        return CityConfig.model_validate(yaml.safe_load(fh))
