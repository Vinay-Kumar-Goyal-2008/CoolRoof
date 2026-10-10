"""M17 Recommendation engine (rules, not an LLM).

Versioned artefacts live in ``rules/<version>/``. A rule whose required fields are
unavailable or stale goes to ``not_evaluated`` with the missing fields. A rule that fires
carries its evidence and a grade equal to the minimum grade of its evidence. Ranking:
Tier 1 = quantified rules with grade A/B; Tier 2 = everything else, ordered by grade.
Grade C never enters Tier 1. Text is template-rendered — no LLM, no invented numbers.
Rules for deferred modules (readiness, fire risk, degradation) are not implemented.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.core.context import WardContext
from packages.core.enums import HeatDomeRisk, HeatType
from packages.core.errors import InputValidationError
from packages.core.params import ParamRegistry

__all__ = ["RuleSet", "load_rules", "recommend"]

_GRADE_ORDER = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class RuleSet:
    version: str
    rules: list[dict[str, Any]]
    evidence: dict[str, dict[str, Any]]
    cooling: list[dict[str, Any]]
    briefs: dict[str, dict[str, Any]]


def load_rules(rules_dir: Path, version: str) -> RuleSet:
    base = rules_dir / version
    rules = json.loads((base / "rules.json").read_text(encoding="utf-8"))
    evidence = {
        e["id"]: e for e in json.loads((base / "evidence.json").read_text(encoding="utf-8"))
    }
    for rule in rules:  # CI gate: every rule must cite evidence that exists
        if not rule.get("evidence_ref") or any(r not in evidence for r in rule["evidence_ref"]):
            raise InputValidationError(f"rule {rule['id']} has empty or unknown evidence_ref")
    return RuleSet(
        version,
        rules,
        evidence,
        json.loads((base / "cooling_options.json").read_text(encoding="utf-8")),
        json.loads((base / "heat_type_briefs.json").read_text(encoding="utf-8")),
    )


Condition = Callable[[WardContext, dict[str, float], dict[str, Any]], bool]


def _conditions(params: ParamRegistry) -> dict[str, Condition]:
    th = params.require("P-THETA-RULE")
    return {
        "R-CR-01": lambda c, p, x: p["priority"] >= th["prio"] and p["roof"] >= th["roof"],
        "R-SO-01": lambda c, p, x: p["roof"] >= th["sol"],
        "R-CP-01": lambda c, p, x: p["exposed"] >= th["exp"] and p["roof"] <= th["few_roofs"],
        "R-GR-01": lambda c, p, x: p["ndvi"] <= 1 - th["bare"] + 0.0 and p["bare"] >= th["bare"],
        "R-EC-01": lambda c, p, x: (
            x.get("heat_type") not in (None, HeatType.NOT_HOT.value, HeatType.UNDETERMINED.value)
        ),
        "R-HD-01": lambda c, p, x: x["heatdome_rank"] >= HeatDomeRisk.ELEVATED.rank,
        "R-EX-01": lambda c, p, x: (
            x["heatdome_rank"] >= HeatDomeRisk.ELEVATED.rank
            and x.get("heat_type") not in (None, HeatType.NOT_HOT.value)
        ),
    }


def city_percentiles(contexts: list[WardContext]) -> dict[str, dict[str, float]]:
    """Within-city percentile of the quantities the rule conditions use."""

    def column(path: str) -> dict[str, float | None]:
        return {c.ward_id: c.value(path) for c in contexts}

    def pct(values: dict[str, float | None]) -> dict[str, float]:
        ok = sorted(v for v in values.values() if v is not None)
        n = len(ok)
        return {
            w: (ok.index(v) / (n - 1) if n > 1 else 0.5) for w, v in values.items() if v is not None
        }

    roof = {
        c.ward_id: (c.value("built_environment.eligible_roof_area_m2") or 0.0)
        / (c.location.area_km2 * 1e6)
        for c in contexts
        if c.field("built_environment.eligible_roof_area_m2").is_available
    }
    return {
        "roof": pct(roof),
        "exposed": pct(column("population.exposed_population")),
        "ndvi": pct(column("environment.ndvi_mean")),
        "bare": pct(column("environment.bare_fraction")),
        "heat": pct(column("heat.mean_dlst_c")),
    }


def recommend(
    ward_id: str,
    contexts: list[WardContext],
    priority_pct: float | None,
    heat_type: str | None,
    rules: RuleSet,
    params: ParamRegistry,
    lang: str = "en",
) -> dict[str, Any]:
    ctx = next(c for c in contexts if c.ward_id == ward_id)
    pcts = city_percentiles(contexts)
    p = {k: pcts[k].get(ward_id, float("nan")) for k in ("roof", "exposed", "ndvi", "bare")}
    p["priority"] = priority_pct if priority_pct is not None else float("nan")
    hd = ctx.value("heat.heatdome_risk")
    extra = {
        "heat_type": heat_type,
        "heatdome_rank": HeatDomeRisk(hd).rank if hd else HeatDomeRisk.UNAVAILABLE.rank,
    }
    conditions = _conditions(params)
    fired: list[dict[str, Any]] = []
    not_evaluated: list[dict[str, Any]] = []
    for rule in rules.rules:
        missing = [f for f in rule["required_fields"] if not ctx.field(f).is_usable_fresh]
        if (
            rule["id"] in ("R-HD-01", "R-EX-01")
            and not ctx.field("heat.heatdome_risk").is_available
        ):
            missing = ["heat.heatdome_risk"]
        if missing or (rule["id"] in ("R-CR-01",) and priority_pct is None):
            not_evaluated.append({"id": rule["id"], "missing_fields": missing or ["priority"]})
            continue
        cond = conditions.get(rule["id"])
        list(p.values())
        if cond is None or any(v != v for k, v in p.items() if k in _needed(rule["id"])):
            not_evaluated.append({"id": rule["id"], "missing_fields": ["city percentiles"]})
            continue
        if not cond(ctx, p, extra):
            continue
        grade = max(
            (rules.evidence[e]["grade"] for e in rule["evidence_ref"]),
            key=lambda g: _GRADE_ORDER[g],
        )
        entry = {
            "id": rule["id"],
            "intervention": rule["intervention"],
            "text": rule["text"][lang].format(
                ward=ctx.location.name if lang == "en" else ctx.location.name_hi
            ),
            "tier": 1 if rule["quantified"] and grade in ("A", "B") else 2,
            "evidence": [
                {k: rules.evidence[e][k] for k in ("id", "title", "url", "grade")}
                for e in rule["evidence_ref"]
            ],
            "evidence_grade": grade,
            "caveats": rule["caveats"],
            "audience": rule["audience"],
        }
        if rule["id"] == "R-EC-01":
            entry["options"] = [
                {
                    "id": o["id"],
                    "name": o["name_i18n"][lang],
                    "type": o["type"],
                    "cost_band": o["cost_band"],
                    "evidence": o["evidence_ref"],
                }
                for o in rules.cooling
                if heat_type in o["suits"]["heat_type"]
            ]
        fired.append(entry)
    fired.sort(key=lambda r: (r["tier"], _GRADE_ORDER[r["evidence_grade"]], r["id"]))
    return {
        "ward_id": ward_id,
        "context_version": ctx.context_version,
        "rules_version": rules.version,
        "recommendations": fired,
        "not_evaluated": not_evaluated,
    }


def _needed(rule_id: str) -> set[str]:
    return {
        "R-CR-01": {"roof", "priority"},
        "R-SO-01": {"roof"},
        "R-CP-01": {"exposed", "roof"},
        "R-GR-01": {"bare", "ndvi"},
    }.get(rule_id, set())
