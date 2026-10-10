"""Shared foundations used by every other package.

Import from the submodules directly (``from packages.core.envelope import
ValueEnvelope``); this package re-exports the most common names for convenience.
"""

from packages.core.envelope import ValueEnvelope
from packages.core.errors import CoolRoofError, ParameterUnavailableError
from packages.core.params import ParamRegistry, ScenarioTriple, load_params

__all__ = [
    "CoolRoofError",
    "ParamRegistry",
    "ParameterUnavailableError",
    "ScenarioTriple",
    "ValueEnvelope",
    "load_params",
]
