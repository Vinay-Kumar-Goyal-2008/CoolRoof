from __future__ import annotations

import pytest

from packages.core.errors import ParameterUnavailableError
from packages.core.params import EvidenceStatus, ParamRegistry

SPEC_SECTION_11_IDS = [
    "P-STQA",
    "P-MINOBS",
    "P-MODIS-RHO",
    "P-TAU",
    "P-W",
    "P-THETA-HEAT",
    "P-THETA-RULE",
    "P-DALB",
    "P-KCOOL",
    "P-KIND",
    "P-PHI",
    "P-CM2",
    "P-PREP",
    "P-U",
    "P-KWMIN",
    "P-AKW",
    "P-KWSTEP",
    "P-TILT",
    "P-AZ",
    "P-LOSS",
    "P-DEG",
    "P-LID",
    "P-GCOST",
    "P-SELF",
    "P-ESC",
    "P-OM",
    "P-INV",
    "P-STALE-POLICY",
    "P-HARD-POLICY",
    "P-COVER",
    "P-FIRE-POLL",
    "P-FIRE-CONF",
    "P-FIRE-RADIUS",
    "P-PA-BUFFER",
    "P-VEG-DROP",
    "P-HPI-W",
    "P-HPI-THETA",
    "P-LOSS-ALERT",
    "P-TREND-MIN",
    "P-BUILT-NA",
    "P-COVMIN",
    "P-HD-T",
    "P-HD-Z",
    "P-HD-DAYS",
    "P-HD-BOX",
    "P-HD-P1",
    "P-HD-P2",
    "P-HD-P3",
    "P-ALERT-RATE",
]


@pytest.mark.parametrize("param_id", SPEC_SECTION_11_IDS)
def test_every_spec_parameter_is_registered(params: ParamRegistry, param_id: str) -> None:
    assert param_id in params


def test_needs_verification_parameters_stay_null(params: ParamRegistry) -> None:
    """Rule 1: [NV] values are never filled in by the build."""
    for pid in params.ids():
        p = params.param(pid)
        if p.status is EvidenceStatus.NEEDS_VERIFICATION:
            assert p.value is None, f"{pid} is [NV] but has a value"


def test_spec_named_defaults_are_used(params: ParamRegistry) -> None:
    assert params.require("P-THETA-HEAT") == {"hi": 0.75, "mid": 0.50, "lo": 0.25}
    assert params.require("P-TREND-MIN") == 8
    assert params.require("P-KWSTEP") == 1.0
    assert params.require("P-LID") == 0.0
    assert params.require("P-STALE-POLICY") == 30
    assert params.require("P-HARD-POLICY") == 90


def test_require_on_null_parameter_raises(params: ParamRegistry) -> None:
    with pytest.raises(ParameterUnavailableError) as exc:
        params.require("P-CM2")
    assert exc.value.param_id == "P-CM2"


def test_scenario_triple(params: ParamRegistry) -> None:
    triple = params.require_triple("P-U")
    assert triple.low < triple.base < triple.high


def test_overrides_do_not_mutate_the_original(params: ParamRegistry) -> None:
    overridden = params.with_overrides({"P-CM2": 250.0})
    assert overridden.require("P-CM2") == 250.0
    assert params.get("P-CM2") is None


def test_unknown_parameter_is_a_programming_error(params: ParamRegistry) -> None:
    with pytest.raises(KeyError):
        params.get("P-DOES-NOT-EXIST")


def test_all_scenario_triples_are_ordered_by_value(params: ParamRegistry) -> None:
    for pid in params.ids():
        value = params.get(pid)
        if isinstance(value, dict) and {"low", "base", "high"} <= value.keys():
            assert value["low"] <= value["base"] <= value["high"], pid
