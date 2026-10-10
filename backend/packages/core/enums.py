"""Every enumeration defined in the build spec (§4.4), in one place.

All enums are ``StrEnum`` so they serialise to their plain string value in JSON
and compare equal to that string.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AdvisoryStatus",
    "Audience",
    "DegradationSignal",
    "ElectricityMode",
    "Eligibility",
    "FieldClass",
    "FireClass",
    "FireConfidence",
    "HabitatPressure",
    "HeatDomeRisk",
    "HeatType",
    "IncidentClass",
    "Language",
    "PaybackStatus",
    "Role",
    "Runtime",
    "Scenario",
    "SettlementType",
    "StepStatus",
    "Suitability",
    "SuryaCheckStatus",
    "TrendClass",
    "UnitType",
    "ValueClass",
    "Verification",
]


class Runtime(StrEnum):
    """Adapter selection, from the ``RUNTIME`` environment variable."""

    LOCAL = "local"
    AWS = "aws"


class ValueClass(StrEnum):
    """Provenance class of a Ward Context value (§0.3)."""

    MEASURED = "measured"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    POLICY = "policy"
    USER = "user"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class FieldClass(StrEnum):
    """Class of every number in a SolarAssessment."""

    FACT = "FACT"
    ASSUMPTION = "ASSUMPTION"
    USER = "USER"
    ESTIMATE = "ESTIMATE"


class Scenario(StrEnum):
    """Scenario labels for ranges (rule 5: ranges, not points)."""

    LOW = "low"
    BASE = "base"
    HIGH = "high"


class SuryaCheckStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class StepStatus(StrEnum):
    """Status of one SuryaCheck orchestrator step (M32)."""

    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class PaybackStatus(StrEnum):
    OK = "ok"
    RANGE_COST_ASSUMED = "payback_range_cost_assumed"
    UNAVAILABLE_NO_TARIFF = "payback_unavailable_no_tariff"
    UNAVAILABLE_STALE_TARIFF = "payback_unavailable_stale_tariff"
    UNAVAILABLE_UNSUPPORTED_DISCOM = "payback_unavailable_unsupported_discom"
    UNAVAILABLE_NO_CONSUMPTION = "payback_unavailable_no_consumption"


class Eligibility(StrEnum):
    UNCONFIRMED = "unconfirmed"
    LIKELY = "likely"
    NOT_ELIGIBLE_PER_ANSWERS = "not_eligible_per_answers"


class HeatType(StrEnum):
    UNDETERMINED = "undetermined"
    NOT_HOT = "not_hot"
    EPISODIC = "episodic"
    DENSE_BUILT_LOW_GREEN = "dense_built_low_green"
    OPEN_BARE_OR_INDUSTRIAL = "open_bare_or_industrial"
    CHRONIC_OTHER = "chronic_other"


class Suitability(StrEnum):
    SUITABLE = "suitable"
    CHECK_OBSTRUCTIONS = "check_obstructions"
    UNSUITABLE = "unsuitable"
    UNKNOWN = "unknown"


class FireClass(StrEnum):
    """Satellite (FIRMS) fire classes (M22)."""

    VEGETATION_FIRE = "vegetation_fire"
    FOREST_FIRE = "forest_fire"
    AGRICULTURAL_BURNING_CANDIDATE = "agricultural_burning_candidate"
    URBAN_THERMAL_ANOMALY_CANDIDATE = "urban_thermal_anomaly_candidate"
    UNCLASSIFIED = "unclassified"
    PERSISTENT_SOURCE = "persistent_source"


class IncidentClass(StrEnum):
    """Staff-reported structure-fire incidents (M22)."""

    STRUCTURE_FIRE_REPORTED = "structure_fire_reported"
    STRUCTURE_FIRE_CONFIRMED = "structure_fire_confirmed"


class FireConfidence(StrEnum):
    LOW = "low"
    NOMINAL = "nominal"
    HIGH = "high"


class TrendClass(StrEnum):
    DECLINING = "declining"
    STABLE = "stable"
    INCREASING = "increasing"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_APPLICABLE = "not_applicable"


class DegradationSignal(StrEnum):
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_APPLICABLE = "not_applicable"


class HabitatPressure(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    INSUFFICIENT_DATA = "insufficient_data"


class HeatDomeRisk(StrEnum):
    NONE = "none"
    WATCH = "watch"
    ELEVATED = "elevated"
    HIGH = "high"
    UNAVAILABLE = "unavailable"

    @property
    def rank(self) -> int:
        """Ordinal used for "≥ elevated" comparisons; ``unavailable`` ranks lowest."""
        return _HEATDOME_RANK[self]


_HEATDOME_RANK = {
    HeatDomeRisk.UNAVAILABLE: -1,
    HeatDomeRisk.NONE: 0,
    HeatDomeRisk.WATCH: 1,
    HeatDomeRisk.ELEVATED: 2,
    HeatDomeRisk.HIGH: 3,
}


class AdvisoryStatus(StrEnum):
    """Alert / advisory lifecycle status."""

    DRAFT = "draft"
    APPROVED = "approved"
    AUTO_INFO = "auto_info"
    PUBLISHED = "published"
    SENT = "sent"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class Audience(StrEnum):
    STAFF = "staff"
    PUBLIC = "public"


class ElectricityMode(StrEnum):
    ADVISORY = "advisory"
    FORECAST = "forecast"


class UnitType(StrEnum):
    WARD = "ward"
    GRID = "grid"


class SettlementType(StrEnum):
    NET_METERING = "net_metering"
    NET_BILLING = "net_billing"


class Verification(StrEnum):
    """Checklist item verification level (M35+36)."""

    OFFICIAL = "official"
    NEEDS_OFFICIAL_CHECK = "needs_official_check"


class Language(StrEnum):
    EN = "en"
    HI = "hi"


class Role(StrEnum):
    """Auth roles (M41), ordered from least to most privileged."""

    ANON = "anon"
    VIEWER = "viewer"
    PLANNER = "planner"
    ADMIN = "admin"

    @property
    def level(self) -> int:
        return _ROLE_LEVEL[self]


_ROLE_LEVEL = {Role.ANON: 0, Role.VIEWER: 1, Role.PLANNER: 2, Role.ADMIN: 3}
