"""M43 Heat-dome / extreme-heat forecast signal (ensemble criteria, no training).

Per member and day: hot surface (Tmax ≥ climatological p90 and anomaly ≥ P-HD-T) and a
Z500 ridge (anomaly ≥ P-HD-Z · σ). An event is ≥ P-HD-DAYS consecutive signal days.
``p_event`` is the share of members with an event; risk is none / watch / elevated / high.
This is a *forecast signal, not an official warning*; official IMD warnings take precedence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from packages.core.enums import HeatDomeRisk
from packages.core.params import ParamRegistry

__all__ = ["HeatDomeForecast", "forecast_heatdome", "load_nwp_fixture"]

DISCLAIMER_EN = "forecast signal, not an official warning"
DISCLAIMER_HI = "पूर्वानुमान संकेत, आधिकारिक चेतावनी नहीं"


@dataclass(frozen=True)
class HeatDomeForecast:
    risk: HeatDomeRisk
    p_event: float | None
    first_day: int | None
    duration: int | None
    tmax_range_c: tuple[float, float] | None
    low_confidence: bool
    issued_at: str | None
    source: str
    criteria: dict[str, float]
    first_date: str | None = None
    criteria_mode: str = "temperature_and_ridge"  # or "temperature_only" (no Z500 available)
    imd_style: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk.value,
            "p_event": self.p_event,
            "first_day": self.first_day,
            "first_date": self.first_date,
            "duration_days": self.duration,
            "tmax_range_c": self.tmax_range_c,
            "low_confidence": self.low_confidence,
            "issued_at": self.issued_at,
            "source": self.source,
            "criteria_params": self.criteria,
            "label_en": DISCLAIMER_EN,
            "label_hi": DISCLAIMER_HI,
            "audience": "staff",
            "official_warning_ref": None,
            "criteria_mode": self.criteria_mode,
            "imd_style": self.imd_style,
        }


def load_nwp_fixture(path: Path | None) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None


def _longest_run(flags: np.ndarray) -> tuple[int, int]:
    best, best_start, run, start = 0, 0, 0, 0
    for i, f in enumerate(flags):
        if f:
            if run == 0:
                start = i
            run += 1
            if run > best:
                best, best_start = run, start
        else:
            run = 0
    return best, best_start


IMD_STYLE_LABEL = "meets IMD-style heatwave criterion in forecast"


def imd_style_check(
    tmax: np.ndarray, t_mean: np.ndarray, criteria: dict[str, Any] | None, region: str = "plains"
) -> dict[str, Any] | None:
    """Share of members whose forecast Tmax meets an IMD-style heatwave definition.

    Never an IMD warning. The criteria are a policy record that needs verification against
    current IMD definitions (spec Appendix B item 10).
    """
    if not criteria:
        return None
    c = criteria["criteria"]
    floor = float(c["min_tmax_c"][region])
    meets = (tmax >= floor) & (
        (tmax - t_mean >= float(c["departure_c"]["heatwave"]))
        | (tmax >= float(c["absolute_tmax_c"]["heatwave"]))
    )
    share = float(meets.any(axis=1).mean())
    return {
        "meets": share >= 0.5,
        "member_share": round(share, 3),
        "label": IMD_STYLE_LABEL,
        "not_an_imd_warning": True,
        "criteria_status": criteria.get("status"),
    }


def forecast_heatdome(
    nwp: dict[str, Any] | None,
    params: ParamRegistry,
    imd_criteria: dict[str, Any] | None = None,
) -> HeatDomeForecast:
    p = {
        k: params.require_float(k)
        for k in ("P-HD-T", "P-HD-Z", "P-HD-DAYS", "P-HD-P1", "P-HD-P2", "P-HD-P3")
    }
    if not nwp:
        return HeatDomeForecast(
            HeatDomeRisk.UNAVAILABLE, None, None, None, None, False, None, "none", p
        )
    members = nwp["members"]
    clim = nwp["climatology"]
    tmax = np.array([m["tmax_c"] for m in members])
    z_missing = any(m.get("z500_box_mean_m") is None for m in members) or any(
        c.get("z500_mean_m") is None for c in clim
    )
    z500 = (
        np.zeros_like(tmax)
        if z_missing
        else np.array([m["z500_box_mean_m"] for m in members], dtype=float)
    )
    t_mean = np.array([c["tmax_mean_c"] for c in clim])
    t_p90 = np.array([c["tmax_p90_c"] for c in clim])
    z_mean = np.zeros(len(clim)) if z_missing else np.array([c["z500_mean_m"] for c in clim])
    z_std = np.ones(len(clim)) if z_missing else np.array([c["z500_std_m"] for c in clim])
    hot = (tmax >= t_p90) & (tmax - t_mean >= p["P-HD-T"])
    ridge = np.ones_like(hot) if z_missing else (z500 - z_mean) >= p["P-HD-Z"] * z_std
    signal = hot & ridge
    need = int(p["P-HD-DAYS"])
    runs = [_longest_run(row) for row in signal]
    has_event = np.array([r[0] >= need for r in runs])
    p_event = float(has_event.mean())
    low_conf = len(members) < 2 or z_missing
    risk = (
        HeatDomeRisk.HIGH
        if p_event >= p["P-HD-P3"]
        else HeatDomeRisk.ELEVATED
        if p_event >= p["P-HD-P2"]
        else HeatDomeRisk.WATCH
        if p_event >= p["P-HD-P1"]
        else HeatDomeRisk.NONE
    )
    if z_missing and risk.rank > HeatDomeRisk.WATCH.rank:
        risk = HeatDomeRisk.WATCH  # temperature-only evidence never reaches elevated/high
    first_day = duration = None
    tmax_range = None
    first_date = None
    if has_event.any():
        starts = [runs[i][1] for i in np.flatnonzero(has_event)]
        first_day = int(np.median(starts)) + 1
        duration = int(np.median([runs[i][0] for i in np.flatnonzero(has_event)]))
        window = tmax[has_event][:, first_day - 1 : first_day - 1 + duration]
        tmax_range = (
            round(float(np.percentile(window, 10)), 1),
            round(float(np.percentile(window, 90)), 1),
        )
        first_date = nwp.get("dates", [None] * 99)[first_day - 1]
    return HeatDomeForecast(
        risk,
        round(p_event, 3),
        first_day,
        duration,
        tmax_range,
        low_conf,
        nwp.get("issued_at"),
        nwp.get("source", "nwp"),
        p,
        first_date,
        criteria_mode="temperature_only" if z_missing else "temperature_and_ridge",
        imd_style=imd_style_check(tmax, t_mean, imd_criteria),
    )
