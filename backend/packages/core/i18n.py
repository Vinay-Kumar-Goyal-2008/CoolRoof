"""Indian number and currency formatting for English and Hindi display strings.

Every number shown in the UI, agent replies and PDFs is formatted here so all
three surfaces show identical strings (M32 contract test).

Hindi strings use Latin digits by default, as is common in official Hindi
documents and because PDF text extraction of Latin digits is exact. Pass
``devanagari_digits=True`` for Devanagari numerals.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from packages.core.enums import Language

__all__ = [
    "format_inr",
    "format_inr_range",
    "format_number",
    "format_range",
    "group_indian",
    "to_devanagari_digits",
]

_TO_DEVANAGARI = str.maketrans("0123456789", "०१२३४५६७८९")
_RANGE_JOINER = {Language.EN: "–", Language.HI: " से "}


def to_devanagari_digits(text: str) -> str:
    return text.translate(_TO_DEVANAGARI)


def group_indian(integer_digits: str) -> str:
    """Apply Indian digit grouping: ``150000`` → ``1,50,000``."""
    negative = integer_digits.startswith("-")
    digits = integer_digits.lstrip("-")
    if len(digits) <= 3:
        grouped = digits
    else:
        head, tail = digits[:-3], digits[-3:]
        pairs: list[str] = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pairs.insert(0, head)
        grouped = ",".join([*pairs, tail])
    return f"-{grouped}" if negative else grouped


def format_number(
    value: float | int | Decimal,
    *,
    decimals: int = 0,
    lang: Language = Language.EN,
    devanagari_digits: bool = False,
) -> str:
    """Indian-grouped number with a fixed number of decimals (half-up rounding)."""
    quantum = Decimal(1).scaleb(-decimals)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{rounded:f}"
    int_part, _, frac = text.partition(".")
    out = group_indian(int_part) + (f".{frac}" if frac else "")
    if lang is Language.HI and devanagari_digits:
        out = to_devanagari_digits(out)
    return out


def format_inr(
    amount: float | int | Decimal,
    *,
    lang: Language = Language.EN,
    decimals: int = 0,
    devanagari_digits: bool = False,
) -> str:
    """Rupee amount, e.g. ``₹1,50,000``."""
    return "₹" + format_number(
        amount, decimals=decimals, lang=lang, devanagari_digits=devanagari_digits
    )


def format_range(
    low: float | int | Decimal,
    high: float | int | Decimal,
    *,
    decimals: int = 0,
    lang: Language = Language.EN,
    unit: str = "",
) -> str:
    """``low–high unit`` (en) or ``low से high unit`` (hi). Equal ends collapse to one value."""
    lo = format_number(low, decimals=decimals, lang=lang)
    hi = format_number(high, decimals=decimals, lang=lang)
    body = lo if lo == hi else f"{lo}{_RANGE_JOINER[lang]}{hi}"
    return f"{body} {unit}".strip()


def format_inr_range(
    low: float | int | Decimal,
    high: float | int | Decimal,
    *,
    lang: Language = Language.EN,
) -> str:
    lo, hi = format_inr(low, lang=lang), format_inr(high, lang=lang)
    return lo if lo == hi else f"{lo}{_RANGE_JOINER[lang]}{hi}"
