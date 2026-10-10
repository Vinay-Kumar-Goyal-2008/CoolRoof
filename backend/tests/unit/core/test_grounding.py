from __future__ import annotations

from decimal import Decimal

import pytest

from packages.core.grounding import check_grounding, extract_numbers

TOOL = {
    "subsidy": {"amount_inr": 78000, "display_en": "₹78,000"},
    "system": {"kw_rec": 3, "specific_yield": 1450.6},
    "payback": {"years_low": 4.2, "years_high": 6.8, "gross_inr": 150000},
    "loss_base": 0.14,
}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("₹78,000", Decimal(78000)),
        ("Rs. 1,50,000", Decimal(150000)),
        ("150,000", Decimal(150000)),
        ("1.5 lakh", Decimal(150000)),
        ("₹७८,०००", Decimal(78000)),
        ("2 करोड़", Decimal(20000000)),
        ("तीन किलोवाट", Decimal(3)),
        ("three kW", Decimal(3)),
    ],
)
def test_extracts_number_forms(text: str, expected: Decimal) -> None:
    values = [n.value for n in extract_numbers(text)]
    assert expected in values


def test_article_one_is_not_a_number() -> None:
    assert extract_numbers("This is one of the hottest wards") == []


def test_grounded_english_reply() -> None:
    text = "A 3 kW system gets a subsidy of ₹78,000; payback is 4.2 to 6.8 years."
    assert check_grounding(text, TOOL).grounded


def test_grounded_hindi_reply_with_devanagari_digits_and_lakh() -> None:
    text = "३ किलोवाट पर ₹७८,००० सब्सिडी मिलेगी, कुल लागत 1.5 लाख है।"
    assert check_grounding(text, TOOL).grounded


def test_rounded_tool_value_is_grounded() -> None:
    assert check_grounding("Specific yield is about 1451 kWh/kWp.", TOOL).grounded


def test_percentage_matches_fraction() -> None:
    assert check_grounding("Base losses are 14%.", TOOL).grounded


def test_invented_number_is_caught() -> None:
    result = check_grounding("Your subsidy will be ₹90,000 and payback 2 years.", TOOL)
    assert not result.grounded
    assert {n.value for n in result.ungrounded} == {Decimal(90000), Decimal(2)}


def test_invented_number_word_is_caught() -> None:
    assert not check_grounding("Payback in five years, guaranteed.", TOOL).grounded


def test_allowed_constants() -> None:
    assert check_grounding("Apply within 30 days.", TOOL, allowed=[30]).grounded
