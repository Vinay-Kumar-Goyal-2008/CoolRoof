"""Helpers that attach provenance (rule 4) to derived values.

Every derived number names its source and the P-* assumption IDs it depends on,
so the UI badge, agent citation and PDF footer can show where it came from.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from packages.core.enums import ValueClass
from packages.core.envelope import ValueEnvelope
from packages.core.params import EvidenceStatus, ParamRegistry
from packages.core.timeutil import today

__all__ = ["assumption_ids", "derived", "from_param"]


def assumption_ids(registry: ParamRegistry, param_ids: Iterable[str]) -> tuple[str, ...]:
    """The subset of ``param_ids`` that are assumptions ([ASSUME] / [NV] / [R])."""
    return tuple(
        sorted(
            pid
            for pid in set(param_ids)
            if registry.param(pid).status is not EvidenceStatus.VERIFIED
        )
    )


def derived(
    value: Any,
    source: str,
    *,
    registry: ParamRegistry | None = None,
    params_used: Iterable[str] = (),
    value_class: ValueClass = ValueClass.DERIVED,
    **extra: Any,
) -> ValueEnvelope:
    """Envelope for a value computed by a deterministic function."""
    ids = assumption_ids(registry, params_used) if registry else tuple(sorted(set(params_used)))
    return ValueEnvelope.of(
        value, value_class, source, processed=today().isoformat(), assumptions=ids, **extra
    )


def from_param(registry: ParamRegistry, param_id: str) -> ValueEnvelope:
    """Envelope for a raw parameter value (``unavailable`` when the parameter is null)."""
    param = registry.param(param_id)
    if not param.is_set:
        return ValueEnvelope.unavailable(
            source=f"config:{param_id}", reason=f"{param_id} not set ({param.status.value})"
        )
    value_class = (
        ValueClass.POLICY if param.status is EvidenceStatus.VERIFIED else ValueClass.ESTIMATED
    )
    return ValueEnvelope.of(
        param.value, value_class, f"config:{param_id}; {param.source}", assumptions=(param_id,)
    )
