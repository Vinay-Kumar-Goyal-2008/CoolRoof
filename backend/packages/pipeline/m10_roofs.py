"""M10 Roof prioritisation.

Eligible roofs (area and footprint-confidence filters, ward not
``buildings_incomplete``) are ranked by benefit per rupee from M11–13. When the
coating cost (``P-CM2``) is unavailable the ranking falls back to benefit alone
and says so. ``local_heat_b`` is the neighbourhood pixel mean — individual roof
temperatures cannot be resolved from Landsat.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from packages.pipeline.m11_coolroof import RoofAssessment

__all__ = ["RankedRoof", "RoofRanking", "rank_roofs"]


@dataclass(frozen=True)
class RankedRoof:
    rank: int
    roof: RoofAssessment


@dataclass(frozen=True)
class RoofRanking:
    ward_id: str
    basis: str  # "benefit_per_rupee" | "benefit_only"
    roofs: list[RankedRoof]
    withheld_reason: str | None = None


def rank_roofs(
    assessments: Sequence[RoofAssessment], ward_id: str, *, buildings_incomplete: bool
) -> RoofRanking:
    """Rank one ward's eligible roofs (rank 1 = best)."""
    if buildings_incomplete:
        return RoofRanking(
            ward_id, "withheld", [], "building footprints are incomplete in this ward"
        )
    eligible = [a for a in assessments if a.ward_id == ward_id and a.eligible]
    if eligible and all(a.bc is not None for a in eligible):
        basis = "benefit_per_rupee"
        ordered = sorted(eligible, key=lambda a: (-a.bc.base, a.building_id))  # type: ignore[union-attr]
    else:
        basis = "benefit_only"
        ordered = sorted(eligible, key=lambda a: (-a.benefit.base, a.building_id))
    return RoofRanking(ward_id, basis, [RankedRoof(i + 1, a) for i, a in enumerate(ordered)])
