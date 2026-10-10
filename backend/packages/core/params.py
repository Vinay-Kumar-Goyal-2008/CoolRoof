"""Parameter registry (§11): every tunable number lives in ``config/params.default.yaml``.

Rule 1 forbids invented values, so code never hard-codes a P-* number. It asks the
registry, which returns the value together with its evidence status and source,
so the value's assumption ID can travel with every number derived from it.

A parameter whose ``value`` is ``null`` (typically ``[NV]``) raises
``ParameterUnavailableError`` from :meth:`ParamRegistry.require`; callers turn
that into an ``unavailable`` output instead of guessing.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from packages.core.enums import Scenario
from packages.core.errors import ParameterUnavailableError

__all__ = [
    "DEFAULT_PARAMS_PATH",
    "EvidenceStatus",
    "Param",
    "ParamRegistry",
    "ScenarioTriple",
    "load_params",
]

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parents[2] / "config" / "params.default.yaml"


class EvidenceStatus(StrEnum):
    """Evidence tags (§0.3)."""

    VERIFIED = "V"
    RECALLED = "R"
    NEEDS_VERIFICATION = "NV"
    ASSUME = "ASSUME"


class ScenarioTriple(BaseModel):
    """A low / base / high triple. Rule 5: ranges, not points."""

    model_config = ConfigDict(frozen=True)

    low: float
    base: float
    high: float

    def get(self, scenario: Scenario) -> float:
        return float(getattr(self, scenario.value))

    def as_dict(self) -> dict[str, float]:
        return {"low": self.low, "base": self.base, "high": self.high}


class Param(BaseModel):
    """One P-* parameter entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    value: Any = None
    unit: str | None = None
    status: EvidenceStatus
    source: str
    modules: tuple[str, ...] = ()
    note: str | None = None
    added_by_implementation: bool = Field(
        default=False,
        description="True for parameters not named in spec §11 that the build needed.",
    )

    @property
    def is_set(self) -> bool:
        return self.value is not None


class ParamRegistry:
    """Read-only view over the parameter file, with optional per-city overrides."""

    def __init__(self, params: Mapping[str, Param]) -> None:
        self._params = dict(params)

    # ------------------------------------------------------------------ lookup
    def __contains__(self, param_id: object) -> bool:
        return param_id in self._params

    def ids(self) -> list[str]:
        return sorted(self._params)

    def param(self, param_id: str) -> Param:
        """Full entry for ``param_id``. Unknown IDs are a programming error."""
        try:
            return self._params[param_id]
        except KeyError as exc:
            raise KeyError(f"unknown parameter id {param_id!r}") from exc

    def get(self, param_id: str) -> Any | None:
        """Value or ``None`` when the parameter is ``null``."""
        return self.param(param_id).value

    def require(self, param_id: str) -> Any:
        """Value, or raise ``ParameterUnavailableError`` when ``null``."""
        value = self.param(param_id).value
        if value is None:
            raise ParameterUnavailableError(param_id)
        return value

    def require_float(self, param_id: str) -> float:
        return float(self.require(param_id))

    def require_triple(self, param_id: str) -> ScenarioTriple:
        """A scenario-triple parameter (``{low, base, high}``)."""
        value = self.require(param_id)
        if not isinstance(value, Mapping):
            raise TypeError(f"{param_id} is not a scenario triple")
        return ScenarioTriple.model_validate(value)

    def optional_triple(self, param_id: str) -> ScenarioTriple | None:
        try:
            return self.require_triple(param_id)
        except ParameterUnavailableError:
            return None

    # ------------------------------------------------------------------ overrides
    def with_overrides(self, overrides: Mapping[str, Any]) -> ParamRegistry:
        """New registry with some values replaced (city config, admin edits, tests).

        An override may be a bare value or a mapping with any ``Param`` fields.
        """
        merged = dict(self._params)
        for param_id, override in overrides.items():
            base = self.param(param_id)
            update = (
                dict(override)
                if isinstance(override, Mapping) and "value" in override
                else {"value": override}
            )
            merged[param_id] = base.model_copy(update=update)
        return ParamRegistry(merged)

    def snapshot(self) -> dict[str, Any]:
        """Plain dict of all values (stored with config versions and run manifests)."""
        return {pid: p.value for pid, p in sorted(self._params.items())}


def _parse(raw: Mapping[str, Any]) -> dict[str, Param]:
    params: dict[str, Param] = {}
    for param_id, entry in raw.items():
        if not isinstance(entry, Mapping):
            raise ValueError(f"parameter {param_id} must be a mapping")
        params[param_id] = Param(id=param_id, **entry)
    return params


def load_params(path: Path | None = None) -> ParamRegistry:
    """Load and validate the parameter file (fails fast on a malformed entry)."""
    file = path or DEFAULT_PARAMS_PATH
    with file.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}
    entries: Mapping[str, Any] = raw.get("parameters", raw)
    return ParamRegistry(_parse(entries))


@lru_cache(maxsize=1)
def default_params() -> ParamRegistry:
    """Process-wide cached default registry."""
    return load_params()
