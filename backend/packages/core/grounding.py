"""Number grounding (rule 3, M33+34, M18+19).

The LLM never computes numbers. Any text it produces is checked here: every
number in the text must appear in the session's tool outputs. Extraction covers
Latin and Devanagari digits, Indian (1,50,000) and western (150,000) grouping,
₹ / Rs / INR prefixes, lakh / crore / thousand multipliers in English and Hindi,
percentages, and English / Hindi number words.

Design choices (documented because they affect what counts as a number):

* "one" / "एक" are only counted when followed by a multiplier or unit, because
  they are mostly used as articles ("one of the wards").
* A text number matches a tool number if they are equal, or if the text number
  equals the tool number rounded to the text's own decimal places
  (tool ``3.84`` grounds text ``3.8``).
* A percentage ``14%`` also matches a tool fraction ``0.14``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

__all__ = [
    "ExtractedNumber",
    "GroundingResult",
    "check_grounding",
    "collect_tool_numbers",
    "extract_numbers",
    "normalise_digits",
]

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_MULTIPLIERS: dict[str, int] = {
    "thousand": 1_000,
    "hazar": 1_000,
    "हज़ार": 1_000,
    "हजार": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "लाख": 100_000,
    "million": 1_000_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "करोड़": 10_000_000,
    "करोड": 10_000_000,
}

_WORD_NUMBERS: dict[str, int] = {
    # English
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    # Hindi
    "दो": 2,
    "तीन": 3,
    "चार": 4,
    "पाँच": 5,
    "पांच": 5,
    "छह": 6,
    "छः": 6,
    "सात": 7,
    "आठ": 8,
    "नौ": 9,
    "दस": 10,
    "बीस": 20,
    "तीस": 30,
    "चालीस": 40,
    "पचास": 50,
    "सौ": 100,
}
_ARTICLE_WORDS: dict[str, int] = {"one": 1, "एक": 1}

_MULT_ALT = "|".join(sorted((re.escape(m) for m in _MULTIPLIERS), key=len, reverse=True))
_NUMBER_RE = re.compile(
    r"(?P<pct_prefix>)"
    r"(?:(?:₹|rs\.?|inr)\s*)?"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    rf"(?:\s*(?P<mult>{_MULT_ALT}))?"
    r"(?P<pct>\s*%)?",
    re.IGNORECASE,
)
_WORD_RE = re.compile(
    r"(?<![\wऀ-ॿ])(?P<word>"
    + "|".join(
        sorted((re.escape(w) for w in {**_WORD_NUMBERS, **_ARTICLE_WORDS}), key=len, reverse=True)
    )
    + r")(?![\wऀ-ॿ])"
    + rf"(?:\s+(?P<mult>{_MULT_ALT}|kw|kilowatt|किलोवाट|percent|प्रतिशत|years?|साल|वर्ष))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedNumber:
    """A number found in text."""

    raw: str
    value: Decimal
    decimals: int
    is_percent: bool = False


@dataclass(frozen=True)
class GroundingResult:
    """Outcome of a grounding check."""

    numbers: tuple[ExtractedNumber, ...]
    ungrounded: tuple[ExtractedNumber, ...] = field(default_factory=tuple)

    @property
    def grounded(self) -> bool:
        return not self.ungrounded


def normalise_digits(text: str) -> str:
    """Convert Devanagari digits to Latin digits."""
    return text.translate(_DEVANAGARI_DIGITS)


def _to_decimal(digits: str) -> tuple[Decimal, int] | None:
    cleaned = digits.replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    decimals = len(cleaned.split(".", 1)[1]) if "." in cleaned else 0
    return value, decimals


def _multiplier(word: str) -> int:
    """Multiplier for an English (case-insensitive) or Hindi multiplier word."""
    return _MULTIPLIERS.get(word.lower(), _MULTIPLIERS.get(word, 1))


def extract_numbers(text: str) -> list[ExtractedNumber]:
    """All numbers in ``text``, normalised to ``Decimal`` values."""
    norm = normalise_digits(text)
    found: list[ExtractedNumber] = []
    spans: list[tuple[int, int]] = []

    for m in _NUMBER_RE.finditer(norm):
        parsed = _to_decimal(m.group("num"))
        if parsed is None:
            continue
        value, decimals = parsed
        mult = m.group("mult")
        if mult:
            value *= _multiplier(mult)
            decimals = 0
        found.append(ExtractedNumber(m.group(0).strip(), value, decimals, bool(m.group("pct"))))
        spans.append(m.span())

    for m in _WORD_RE.finditer(norm):
        if any(start <= m.start() < end for start, end in spans):
            continue
        word = m.group("word").lower() if m.group("word").isascii() else m.group("word")
        follower = m.group("mult")
        if word in _ARTICLE_WORDS and not follower:
            continue
        base = _WORD_NUMBERS.get(word, _ARTICLE_WORDS.get(word, 0))
        value = Decimal(base)
        if follower:
            value *= _multiplier(follower)
        is_pct = bool(follower) and follower.lower() in ("percent", "प्रतिशत")
        found.append(ExtractedNumber(m.group(0).strip(), value, 0, is_pct))
    return found


def collect_tool_numbers(tool_outputs: Any) -> set[Decimal]:
    """Every number inside tool outputs: JSON numbers and numbers inside strings."""
    numbers: set[Decimal] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, int | float):
            try:
                numbers.add(Decimal(str(node)))
            except InvalidOperation:
                return
        elif isinstance(node, Decimal):
            numbers.add(node)
        elif isinstance(node, str):
            numbers.update(n.value for n in extract_numbers(node))
        elif isinstance(node, Mapping):
            for value in node.values():
                walk(value)
        elif isinstance(node, Iterable):
            for item in node:
                walk(item)

    walk(tool_outputs)
    return numbers


def _matches(candidate: ExtractedNumber, source: Decimal) -> bool:
    targets = [source]
    if candidate.is_percent:
        targets.append(source * 100)
    for target in targets:
        if candidate.value == target:
            return True
        quantum = Decimal(1).scaleb(-candidate.decimals)
        try:
            if target.quantize(quantum, rounding=ROUND_HALF_UP) == candidate.value:
                return True
        except InvalidOperation:
            continue
    return False


def check_grounding(
    text: str,
    tool_outputs: Any,
    *,
    allowed: Iterable[Decimal | int | float] = (),
) -> GroundingResult:
    """Check that every number in ``text`` appears in ``tool_outputs``.

    Args:
        text: Response text (any language).
        tool_outputs: The session's tool outputs (any JSON-like structure).
        allowed: Extra numbers that are always permitted (e.g. template constants).

    Returns:
        A ``GroundingResult``; ``grounded`` is False if any number is unsupported.
    """
    sources = collect_tool_numbers(tool_outputs) | {Decimal(str(a)) for a in allowed}
    numbers = extract_numbers(text)
    ungrounded = [n for n in numbers if not any(_matches(n, s) for s in sources)]
    return GroundingResult(tuple(numbers), tuple(ungrounded))
