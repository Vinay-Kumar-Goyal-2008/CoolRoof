"""M43 evaluation: hit rate, false-alarm ratio and Brier score for forecast-signal hindcasts.

Feed it ``(p_event, observed_event)`` pairs from archived forecasts (or reanalysis as a perfect-forecast
proxy), e.g. the 2022 and 2024 Indian heatwaves. ``sensitivity`` re-runs the criteria with one
P-HD-* parameter changed at a time so thresholds can be tuned from evidence, not guessed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from packages.core.params import ParamRegistry
from packages.pipeline.m43_heatdome import forecast_heatdome

__all__ = ["score_forecasts", "sensitivity"]


def score_forecasts(
    pairs: Iterable[tuple[float, bool]], p_threshold: float = 0.4
) -> dict[str, Any]:
    """Contingency scores at ``p_threshold`` (default = the 'elevated' probability)."""
    rows = list(pairs)
    if not rows:
        return {"n": 0}
    hits = sum(1 for p, o in rows if p >= p_threshold and o)
    misses = sum(1 for p, o in rows if p < p_threshold and o)
    false_alarms = sum(1 for p, o in rows if p >= p_threshold and not o)
    warned = hits + false_alarms
    observed = hits + misses
    return {
        "n": len(rows),
        "hit_rate": hits / observed if observed else None,
        "false_alarm_ratio": false_alarms / warned if warned else None,
        "brier": sum((p - float(o)) ** 2 for p, o in rows) / len(rows),
        "events_observed": observed,
    }


def sensitivity(
    nwp: dict[str, Any], params: ParamRegistry, grid: dict[str, Sequence[float]]
) -> list[dict[str, Any]]:
    """Risk and event probability when each P-HD-* parameter is varied on its own."""
    out = []
    for pid, values in grid.items():
        for v in values:
            f = forecast_heatdome(nwp, params.with_overrides({pid: v}))
            out.append({"param": pid, "value": v, "risk": f.risk.value, "p_event": f.p_event})
    return out
