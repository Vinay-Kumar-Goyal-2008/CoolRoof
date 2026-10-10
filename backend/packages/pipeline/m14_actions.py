"""M14 Municipal action ranking.

Wards by priority, then buildings by benefit per rupee, under a budget
(base-scenario cost ≤ budget). Produces the action list and CSV with columns
``rank, ward, building_id, action, cost_range, people_protected_range,
confidence, assumptions``. Same config + data → byte-identical CSV (hash).
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass

from packages.core.errors import ParameterUnavailableError
from packages.core.i18n import format_inr_range, format_range
from packages.pipeline.m09_priority import WardScore
from packages.pipeline.m11_coolroof import ZERO, Range, RoofAssessment

__all__ = ["CSV_COLUMNS", "ActionPlan", "ActionRow", "build_action_plan"]

CSV_COLUMNS = (
    "rank",
    "ward",
    "building_id",
    "action",
    "cost_range",
    "people_protected_range",
    "confidence",
    "assumptions",
)
ACTION = "cool_roof_coating"


@dataclass(frozen=True)
class ActionRow:
    rank: int
    ward_id: str
    building_id: str
    cost: Range
    protected: Range
    confidence: float
    assumptions: tuple[str, ...]
    ward_priority_rank: int

    def csv_row(self) -> list[str]:
        return [
            str(self.rank),
            self.ward_id,
            self.building_id,
            ACTION,
            format_inr_range(round(self.cost.low), round(self.cost.high)),
            format_range(self.protected.low, self.protected.high, decimals=0),
            f"{self.confidence:.2f}",
            ";".join(self.assumptions),
        ]


@dataclass(frozen=True)
class ActionPlan:
    budget_inr: float
    rows: list[ActionRow]
    total_cost: Range
    total_protected: Range
    skipped_wards: dict[str, str]

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in self.rows:
            writer.writerow(row.csv_row())
        return buf.getvalue()

    @property
    def csv_hash(self) -> str:
        return hashlib.sha256(self.to_csv().encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, object]:
        return {
            "budget_inr": self.budget_inr,
            "roofs": len(self.rows),
            "total_cost_inr": self.total_cost.as_dict(0),
            "people_protected": self.total_protected.as_dict(0),
            "skipped_wards": self.skipped_wards,
        }


def build_action_plan(
    scores: Sequence[WardScore],
    roofs: Sequence[RoofAssessment],
    budget_inr: float,
    *,
    incomplete_wards: set[str],
    ward_filter: set[str] | None = None,
) -> ActionPlan:
    """City-wide plan. Raises ``ParameterUnavailableError`` when costs are unavailable."""
    by_ward: dict[str, list[RoofAssessment]] = {}
    for roof in roofs:
        if roof.eligible:
            by_ward.setdefault(roof.ward_id, []).append(roof)
    if any(r.cost_inr is None or r.bc is None for rs in by_ward.values() for r in rs):
        raise ParameterUnavailableError("P-CM2")

    rows: list[ActionRow] = []
    skipped: dict[str, str] = {}
    spent = 0.0
    total_cost, total_protected = ZERO, ZERO
    ranked_scores = sorted((s for s in scores if s.rank is not None), key=lambda s: s.rank or 0)
    for score in ranked_scores:
        ward = score.ward_id
        if ward_filter and ward not in ward_filter:
            continue
        if ward in incomplete_wards:
            skipped[ward] = "buildings_incomplete"
            continue
        for roof in sorted(by_ward.get(ward, []), key=lambda r: (-r.bc.base, r.building_id)):  # type: ignore[union-attr]
            cost = roof.cost_inr
            assert cost is not None
            if spent + cost.base > budget_inr:
                continue
            spent += cost.base
            total_cost = total_cost + cost
            total_protected = total_protected + roof.protected
            rows.append(
                ActionRow(
                    rank=len(rows) + 1,
                    ward_id=ward,
                    building_id=roof.building_id,
                    cost=cost,
                    protected=roof.protected,
                    confidence=score.score_confidence,
                    assumptions=roof.assumptions,
                    ward_priority_rank=score.rank or 0,
                )
            )
    return ActionPlan(budget_inr, rows, total_cost, total_protected, skipped)
