from __future__ import annotations

import pytest

from packages.core.enums import Language
from packages.core.i18n import format_inr, format_inr_range, format_number, format_range


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "₹0"),
        (999, "₹999"),
        (78000, "₹78,000"),
        (150000, "₹1,50,000"),
        (12345678, "₹1,23,45,678"),
    ],
)
def test_indian_grouping(value: int, expected: str) -> None:
    assert format_inr(value) == expected


def test_decimals_round_half_up() -> None:
    assert format_number(2.25, decimals=1) == "2.3"
    assert format_number(1234567.891, decimals=2) == "12,34,567.89"


def test_hindi_devanagari_digits_option() -> None:
    assert format_inr(78000, lang=Language.HI, devanagari_digits=True) == "₹७८,०००"


def test_ranges() -> None:
    assert format_range(4.2, 6.8, decimals=1, unit="yr") == "4.2–6.8 yr"
    assert format_range(4.2, 6.8, decimals=1, lang=Language.HI, unit="वर्ष") == "4.2 से 6.8 वर्ष"
    assert format_inr_range(78000, 78000) == "₹78,000"
