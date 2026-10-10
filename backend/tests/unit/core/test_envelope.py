from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.core.enums import ValueClass
from packages.core.envelope import ValueEnvelope


def test_serialises_with_spec_field_name_class() -> None:
    env = ValueEnvelope.of(3.8, ValueClass.DERIVED, "landsat_c2l2_st", resolution_m=30)
    data = env.to_json_dict()
    assert data["class"] == "derived"
    assert data["value"] == 3.8
    assert "cls" not in data


def test_round_trips_from_spec_json() -> None:
    raw = {
        "value": 3.8,
        "class": "derived",
        "source": "landsat_c2l2_st; season=2026-MarJun; years=3",
        "observed": "2024-03..2026-06",
        "processed": "2026-10-07",
        "resolution_m": 30,
        "confidence": 0.7,
        "stale_after": "2027-07-01",
    }
    env = ValueEnvelope.model_validate(raw)
    assert env.cls is ValueClass.DERIVED
    assert env.to_json_dict()["stale_after"] == "2027-07-01"


def test_unavailable_has_no_value_and_a_reason() -> None:
    env = ValueEnvelope.unavailable("worldpop", "dataset not loaded")
    assert env.value is None
    assert not env.is_available
    assert env.as_float() is None


def test_unavailable_with_a_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ValueEnvelope(value=0, cls=ValueClass.UNAVAILABLE, source="x", reason="missing")


def test_available_class_without_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ValueEnvelope(value=None, cls=ValueClass.MEASURED, source="x")


def test_mark_stale_keeps_value_and_flags_it() -> None:
    env = ValueEnvelope.of(0.42, ValueClass.MEASURED, "ndvi").mark_stale()
    assert env.cls is ValueClass.STALE
    assert env.value == 0.42
    assert env.is_available and not env.is_usable_fresh


def test_confidence_must_be_a_probability() -> None:
    with pytest.raises(ValidationError):
        ValueEnvelope.of(1.0, ValueClass.DERIVED, "x", confidence=1.5)
