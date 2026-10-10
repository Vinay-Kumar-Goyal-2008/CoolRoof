"""M15 Heat-type classification (rule-based, precedence-ordered) + authority brief.

Gate: if ΔLST, persistence, NDVI or built fraction is unavailable/stale the type is
``undetermined`` and the missing fields are listed. Otherwise percentiles within the
city and the first matching rule win. ML clustering never overwrites these labels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd

from packages.core.context import WardContext
from packages.core.enums import HeatType
from packages.core.params import ParamRegistry

__all__ = ["HeatTypeResult", "classify_wards"]

REQUIRED = {
    "mean_dlst_c": "heat.mean_dlst_c",
    "persistence": "heat.persistence",
    "ndvi": "environment.ndvi_mean",
    "built": "built_environment.built_fraction",
}


@dataclass(frozen=True)
class HeatTypeResult:
    ward_id: str
    heat_type: HeatType
    confidence: float | None
    evidence: dict[str, object] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


def _pct(series: pd.Series) -> pd.Series:
    return series.rank(method="average", pct=False).sub(1).div(max(len(series.dropna()) - 1, 1))


def classify_wards(contexts: Sequence[WardContext], params: ParamRegistry) -> list[HeatTypeResult]:
    theta = params.require("P-THETA-HEAT")
    hi, mid, lo = float(theta["hi"]), float(theta["mid"]), float(theta["lo"])
    rows = {
        c.ward_id: {
            k: (c.value(p) if c.field(p).is_usable_fresh else None) for k, p in REQUIRED.items()
        }
        for c in contexts
    }
    raw = pd.DataFrame.from_dict(rows, orient="index", dtype=float)
    pct = raw.apply(_pct)
    conf = {
        c.ward_id: min(
            [c.field(p).confidence or 1.0 for p in REQUIRED.values() if c.field(p).is_available]
            or [0.0]
        )
        for c in contexts
    }
    out: list[HeatTypeResult] = []
    for ward_id in raw.index:
        missing = tuple(k for k in REQUIRED if pd.isna(raw.at[ward_id, k]))
        if missing:
            out.append(HeatTypeResult(ward_id, HeatType.UNDETERMINED, None, {}, missing))
            continue
        d, per, ndvi, built = (
            float(pct.at[ward_id, k]) for k in ("mean_dlst_c", "persistence", "ndvi", "built")
        )
        if d < hi:
            label, margins = HeatType.NOT_HOT, [hi - d]
        elif per <= lo:
            label, margins = HeatType.EPISODIC, [d - hi, lo - per]
        elif built >= hi and ndvi <= lo:
            label, margins = HeatType.DENSE_BUILT_LOW_GREEN, [d - hi, built - hi, lo - ndvi]
        elif built <= mid and ndvi <= lo:
            label, margins = HeatType.OPEN_BARE_OR_INDUSTRIAL, [d - hi, mid - built, lo - ndvi]
        else:
            label, margins = HeatType.CHRONIC_OTHER, [d - hi]
        denom = max(hi, 1 - hi)
        margin = min(1.0, max(0.0, min(abs(m) for m in margins) / denom))
        out.append(
            HeatTypeResult(
                ward_id,
                label,
                round(conf[ward_id] * margin, 3),
                {
                    "percentiles": {k: round(float(pct.at[ward_id, k]), 3) for k in REQUIRED},
                    "thresholds": {"hi": hi, "mid": mid, "lo": lo},
                    "rule": label.value,
                },
            )
        )
    return out
