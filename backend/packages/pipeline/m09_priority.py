"""M9 Ward priority score.

Components (within-city normalised to [0, 1]):
``H = pct(ΔLST_mean)``, ``P = pct(persistence)``, ``E = pct(exposed_pop)``,
``V = 1 − pct(NDVI)``, ``R = pct(eligible roof area / ward area)``, ``F`` feasibility gate.

``Need = (a_H·H + a_P·P + a_E·E + a_V·V) / Σa`` and
``Priority = Need · (0.5 + 0.5·R) · F``.

Normalisation is the percentile rank; below ``P-SMALL-CITY`` wards it is the
z-score mapped through the standard normal CDF (spec: "use z-score when the
city has fewer than ~30 wards"). A missing variable is dropped and the weights
renormalised; if both heat and exposure are missing the ward is unscored. A
missing R uses the neutral multiplier at the median roof opportunity
(0.5 + 0.5·0.5) and is flagged.

Sensitivity: Dirichlet weight draws → rank interval and top-k stability;
leave-one-variable-out and an additive alternative, both as Spearman ρ.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from packages.core.context import WardContext
from packages.core.params import ParamRegistry

__all__ = ["COMPONENTS", "PriorityResult", "WardScore", "normalise", "score_wards"]

COMPONENTS = ("H", "P", "E", "V", "R")
NEED_COMPONENTS = ("H", "P", "E", "V")
_SOURCES = {
    "H": "heat.mean_dlst_c",
    "P": "heat.persistence",
    "E": "population.exposed_population",
    "V": "environment.ndvi_mean",
}
_NEUTRAL_R = 0.5


@dataclass
class WardScore:
    ward_id: str
    priority: float | None
    need: float | None
    components: dict[str, float | None]
    variables_used: list[str]
    score_confidence: float
    rank: int | None = None
    rank_interval: tuple[int, int] | None = None
    top_k_share: float | None = None
    flags: list[str] = field(default_factory=list)
    unscored_reason: str | None = None


@dataclass
class PriorityResult:
    scores: list[WardScore]
    normalisation: str
    weights: dict[str, float]
    sensitivity: dict[str, object]

    def by_ward(self) -> dict[str, WardScore]:
        return {s.ward_id: s for s in self.scores}


def normalise(values: pd.Series, method: str) -> pd.Series:
    """Map available values to [0, 1]; NaN stays NaN."""
    ok = values.dropna()
    out = pd.Series(np.nan, index=values.index)
    if ok.empty:
        return out
    if len(ok) == 1:
        out[ok.index] = 0.5
        return out
    if method == "percentile":
        ranks = ok.rank(method="average")
        out[ok.index] = (ranks - 1) / (len(ok) - 1)
    else:
        sigma = ok.std(ddof=0)
        z = (ok - ok.mean()) / sigma if sigma > 0 else ok * 0.0
        out[ok.index] = stats.norm.cdf(z)
    return out


def _raw_variables(contexts: Sequence[WardContext]) -> pd.DataFrame:
    rows = {}
    for ctx in contexts:
        row = {k: ctx.value(path) for k, path in _SOURCES.items()}
        eligible = ctx.value("built_environment.eligible_roof_area_m2")
        area_km2 = ctx.location.area_km2
        row["R"] = eligible / (area_km2 * 1e6) if eligible is not None and area_km2 else None
        rows[ctx.ward_id] = row
    return pd.DataFrame.from_dict(rows, orient="index", dtype=float)


def _components(raw: pd.DataFrame, method: str) -> pd.DataFrame:
    comp = pd.DataFrame(index=raw.index)
    for key in COMPONENTS:
        comp[key] = normalise(raw[key], method)
    comp["V"] = 1.0 - comp["V"]
    return comp


def _priority(
    comp: pd.DataFrame, weights: Mapping[str, float], feas: pd.Series, use_r: bool = True
) -> tuple[pd.Series, pd.Series]:
    w = pd.Series({k: weights[k] for k in NEED_COMPONENTS})
    present = comp[list(NEED_COMPONENTS)].notna()
    num = (comp[list(NEED_COMPONENTS)].fillna(0.0) * w).sum(axis=1)
    den = (present * w).sum(axis=1)
    need = num / den.replace(0, np.nan)
    r = comp["R"].fillna(_NEUTRAL_R) if use_r else pd.Series(1.0, index=comp.index)
    mult = (0.5 + 0.5 * r) if use_r else r
    unscored = comp["H"].isna() & comp["E"].isna()
    priority = (need * mult * feas).where(~unscored)
    return priority, need.where(~unscored)


def _ranks(priority: pd.Series) -> pd.Series:
    """Rank 1 = highest priority; ties broken by ward id for determinism."""
    ordered = priority.dropna().reset_index()
    ordered.columns = ["ward_id", "p"]
    ordered = ordered.sort_values(["p", "ward_id"], ascending=[False, True])
    return pd.Series(np.arange(1, len(ordered) + 1), index=ordered["ward_id"].to_numpy())


def score_wards(
    contexts: Sequence[WardContext],
    params: ParamRegistry,
    feasibility: Mapping[str, float] | None = None,
) -> PriorityResult:
    weights = {k: float(v) for k, v in params.require("P-W").items()}
    weights = {k.removeprefix("a_"): v for k, v in weights.items()}
    method = "percentile" if len(contexts) >= params.require_float("P-SMALL-CITY") else "zscore_cdf"
    raw = _raw_variables(contexts)
    comp = _components(raw, method)
    default_f = params.require_float("P-F")
    feas = pd.Series({w: float((feasibility or {}).get(w, default_f)) for w in comp.index})

    priority, need = _priority(comp, weights, feas)
    ranks = _ranks(priority)

    # ---------------- Dirichlet sensitivity
    cfg = params.require("P-W-DIRICHLET")
    rng = np.random.default_rng(int(cfg["seed"]))
    base_w = np.array([weights[k] for k in NEED_COMPONENTS])
    alpha = float(cfg["concentration"]) * base_w / base_w.sum() * len(base_w)
    scored = ranks.index.tolist()
    k_top = min(10, max(1, len(scored)))
    draws = int(cfg["draws"])
    rank_draws = np.zeros((draws, len(scored)), dtype=int)
    for d, sample in enumerate(rng.dirichlet(alpha, size=draws)):
        p, _ = _priority(comp, dict(zip(NEED_COMPONENTS, sample, strict=True)), feas)
        rank_draws[d] = _ranks(p).reindex(scored).to_numpy()
    lo: Sequence[int] = np.percentile(rank_draws, 5, axis=0).round().astype(int) if scored else []
    hi: Sequence[int] = np.percentile(rank_draws, 95, axis=0).round().astype(int) if scored else []
    top_share: Sequence[float] = (rank_draws <= k_top).mean(axis=0) if scored else []

    # ---------------- leave-one-variable-out and additive alternative
    loo: dict[str, float] = {}
    for var in COMPONENTS:
        reduced = comp.copy()
        if var == "R":
            p, _ = _priority(reduced, weights, feas, use_r=False)
        else:
            reduced[var] = np.nan
            p, _ = _priority(reduced, weights, feas)
        common = priority.dropna().index.intersection(p.dropna().index)
        loo[var] = (
            float(stats.spearmanr(priority[common], p[common]).statistic)
            if len(common) > 2
            else float("nan")
        )
    a_r = float(np.mean(list(weights.values())))
    additive = (
        comp[list(NEED_COMPONENTS)].mul(pd.Series(weights)).sum(axis=1)
        + a_r * comp["R"].fillna(_NEUTRAL_R)
    ) / (sum(weights.values()) + a_r)
    common = priority.dropna().index
    additive_rho = (
        float(stats.spearmanr(priority[common], additive[common]).statistic)
        if len(common) > 2
        else float("nan")
    )

    ctx_conf = {c.ward_id: c.data_quality.context_confidence for c in contexts}
    interval = {w: (int(lo[i]), int(hi[i])) for i, w in enumerate(scored)}
    top = {w: float(top_share[i]) for i, w in enumerate(scored)}
    out: list[WardScore] = []
    total_w = sum(weights[k] for k in NEED_COMPONENTS)
    for ward_id in comp.index:
        row = comp.loc[ward_id]
        used = [k for k in COMPONENTS if pd.notna(row[k])]
        flags = [] if pd.notna(row["R"]) else ["roof_opportunity_unavailable"]
        share = sum(weights[k] for k in NEED_COMPONENTS if k in used) / total_w
        comps = {k: (round(float(row[k]), 4) if pd.notna(row[k]) else None) for k in COMPONENTS}
        comps["F"] = float(feas[ward_id])
        p = priority.get(ward_id)
        unscored = p is None or pd.isna(p)
        out.append(
            WardScore(
                ward_id=ward_id,
                priority=None if unscored else round(float(p), 4),
                need=None if unscored else round(float(need[ward_id]), 4),
                components=comps,
                variables_used=used,
                score_confidence=round(share * ctx_conf.get(ward_id, 1.0), 3),
                rank=int(ranks[ward_id]) if ward_id in ranks.index else None,
                rank_interval=interval.get(ward_id),
                top_k_share=round(top[ward_id], 3) if ward_id in top else None,
                flags=flags,
                unscored_reason="heat and exposure both unavailable" if unscored else None,
            )
        )
    out.sort(key=lambda s: (s.rank is None, s.rank or 0, s.ward_id))
    return PriorityResult(
        scores=out,
        normalisation=method,
        weights={**weights, "concentration": float(cfg["concentration"])},
        sensitivity={
            "draws": draws,
            "top_k": k_top,
            "leave_one_out_spearman": loo,
            "additive_spearman": additive_rho,
        },
    )
