"""Wording rules (§0.1 rule 10), enforced by tests and by output checks.

The spec's required sentences contain words the denylist forbids
("…not a measured biodiversity loss", "indicator, not diagnosis",
"…not an official warning"). So the checker:

1. removes the exact required phrases before matching, and
2. ignores a forbidden term when a negation ("not", "never", "≠", "नहीं")
   appears within a few words before it.

Each rule applies only within its scope, so e.g. "due to" is only banned when
describing heat drivers, not in "unavailable due to missing tariff".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "REQUIRED_PHRASES",
    "WordingScope",
    "WordingViolation",
    "assert_wording",
    "check_wording",
]


class WordingScope(StrEnum):
    LST = "lst"  # anything describing Landsat surface temperature
    DRIVERS = "drivers"  # M16 driver attribution text
    ENVIRONMENT = "environment"  # M23 / M24 outputs
    FORECAST = "forecast"  # M43 outputs


REQUIRED_PHRASES: dict[str, str] = {
    "lst": "surface temperature at a late-morning satellite pass",
    "forecast_public": "forecast signal, not an official warning",
    "m23": "habitat pressure indicator, unverified — not a measured biodiversity loss",
    "m24": "indicator, not diagnosis",
    "imd_style": "meets IMD-style heatwave criterion in forecast",
}

_NEGATION_RE = re.compile(r"(\bnot\b|\bnever\b|\bno\b|≠|नहीं|न कि)", re.IGNORECASE)
_NEGATION_WINDOW_CHARS = 40


@dataclass(frozen=True)
class _Rule:
    scope: WordingScope
    pattern: re.Pattern[str]
    advice: str


_RULES: tuple[_Rule, ...] = (
    _Rule(
        WordingScope.LST,
        re.compile(r"\bair[- ]temperature\b", re.I),
        'LST is "surface temperature at a late-morning satellite pass"',
    ),
    _Rule(
        WordingScope.LST,
        re.compile(r"\breal[- ]time temperature\b", re.I),
        "Landsat is episodic, not real-time",
    ),
    _Rule(
        WordingScope.DRIVERS,
        re.compile(r"\bcaused by\b|\bdue to\b|\bcauses\b", re.I),
        'drivers are "associated with"',
    ),
    _Rule(
        WordingScope.DRIVERS,
        re.compile(r"कारण\s+से|की\s+वजह\s+से"),
        'Hindi: use "से जुड़ा" (associated with)',
    ),
    _Rule(
        WordingScope.ENVIRONMENT,
        re.compile(
            r"\bbiodiversity loss\b|\bspecies loss\b|"
            r"\bloss of (?:species|biodiversity)\b",
            re.I,
        ),
        'use "habitat pressure indicator"',
    ),
    _Rule(
        WordingScope.ENVIRONMENT,
        re.compile(r"\bdiagnos(?:is|ed|e)\b|\bconfirmed degradation\b", re.I),
        'use "indicator, not diagnosis"',
    ),
    _Rule(
        WordingScope.FORECAST,
        re.compile(r"\bofficial warning\b", re.I),
        'M43 output is a "forecast signal"',
    ),
    _Rule(
        WordingScope.FORECAST,
        re.compile(r"\bpredict(?:ion|s|ed)?\b", re.I),
        'use "forecast signal"',
    ),
)


@dataclass(frozen=True)
class WordingViolation:
    scope: WordingScope
    term: str
    advice: str
    position: int


def _strip_required(text: str) -> str:
    for phrase in REQUIRED_PHRASES.values():
        text = re.sub(re.escape(phrase), " " * len(phrase), text, flags=re.IGNORECASE)
    return text


def _is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - _NEGATION_WINDOW_CHARS) : start]
    return bool(_NEGATION_RE.search(window))


def check_wording(text: str, scopes: set[WordingScope] | None = None) -> list[WordingViolation]:
    """Return every wording violation in ``text`` for the given scopes (default: all)."""
    active = scopes or set(WordingScope)
    cleaned = _strip_required(text)
    violations: list[WordingViolation] = []
    for rule in _RULES:
        if rule.scope not in active:
            continue
        for m in rule.pattern.finditer(cleaned):
            if not _is_negated(cleaned, m.start()):
                violations.append(WordingViolation(rule.scope, m.group(0), rule.advice, m.start()))
    return violations


def assert_wording(text: str, scopes: set[WordingScope] | None = None) -> None:
    """Raise ``ValueError`` listing violations (used by generators before output)."""
    violations = check_wording(text, scopes)
    if violations:
        detail = "; ".join(f"'{v.term}' ({v.scope}): {v.advice}" for v in violations)
        raise ValueError(f"wording rule violation: {detail}")
