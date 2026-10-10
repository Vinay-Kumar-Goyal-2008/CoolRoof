"""Value envelope (§4.1): every Ward Context value carries its provenance.

A value is never a bare number. It is wrapped with its class, source, dates,
resolution, confidence and the assumption IDs it depends on. Missing data is an
envelope with ``class = "unavailable"`` and a ``reason`` — never ``0``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.core.enums import ValueClass

__all__ = ["Scalar", "ValueEnvelope"]

Scalar = float | int | str | bool | None


class ValueEnvelope(BaseModel):
    """A single provenance-tagged value.

    The JSON field is ``class`` (a Python keyword), exposed here as ``cls``.
    Always serialise with ``by_alias=True`` (``to_json_dict`` does this).
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True, extra="forbid")

    value: Any = None
    cls: ValueClass = Field(alias="class")
    source: str
    observed: str | None = None
    processed: str = Field(default_factory=lambda: date.today().isoformat())
    resolution_m: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    stale_after: str | None = None
    assumptions: tuple[str, ...] = ()
    reason: str | None = None
    alt_value: Any = None

    @model_validator(mode="after")
    def _check_consistency(self) -> ValueEnvelope:
        if self.cls is ValueClass.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("an 'unavailable' envelope must not carry a value")
            if not self.reason:
                raise ValueError("an 'unavailable' envelope must state a reason")
        elif self.value is None:
            raise ValueError(f"a '{self.cls}' envelope needs a value; use unavailable() instead")
        return self

    # ------------------------------------------------------------------ constructors
    @classmethod
    def unavailable(cls, source: str, reason: str, **extra: Any) -> ValueEnvelope:
        """Envelope for missing data. Rule 2: never ``0``, never a national default."""
        return cls(value=None, cls=ValueClass.UNAVAILABLE, source=source, reason=reason, **extra)

    @classmethod
    def of(cls, value: Any, value_class: ValueClass, source: str, **extra: Any) -> ValueEnvelope:
        """Envelope for an available value of the given class."""
        return cls(value=value, cls=value_class, source=source, **extra)

    # ------------------------------------------------------------------ queries
    @property
    def is_available(self) -> bool:
        """True when the value can be used (stale values are still usable, but flagged)."""
        return self.cls is not ValueClass.UNAVAILABLE

    @property
    def is_usable_fresh(self) -> bool:
        """True when the value is available and not stale."""
        return self.cls not in (ValueClass.UNAVAILABLE, ValueClass.STALE)

    def as_float(self) -> float | None:
        """The value as a float, or ``None`` when unavailable."""
        if not self.is_available or self.value is None:
            return None
        return float(self.value)

    def mark_stale(self) -> ValueEnvelope:
        """Copy of this envelope flipped to ``stale`` (used by the M8.5 staleness job)."""
        if not self.is_available:
            return self
        return self.model_copy(update={"cls": ValueClass.STALE})

    def to_json_dict(self) -> dict[str, Any]:
        """Serialise with the spec's field names, dropping empty optional fields."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
