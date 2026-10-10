from __future__ import annotations

import pytest

from packages.core.wording import REQUIRED_PHRASES, WordingScope, check_wording


@pytest.mark.parametrize("phrase", list(REQUIRED_PHRASES.values()))
def test_required_phrases_never_violate(phrase: str) -> None:
    assert check_wording(f"Note: {phrase}.") == []


@pytest.mark.parametrize(
    ("text", "scope"),
    [
        ("Ward 7 heat is caused by dense roofs.", WordingScope.DRIVERS),
        ("Heat here is due to low tree cover.", WordingScope.DRIVERS),
        ("Severe biodiversity loss in the sanctuary.", WordingScope.ENVIRONMENT),
        ("Soil degradation diagnosis: strong.", WordingScope.ENVIRONMENT),
        ("IMD-grade official warning: heat dome.", WordingScope.FORECAST),
        ("Our prediction says 46 °C.", WordingScope.FORECAST),
        ("The air temperature in ward 3 was 44 °C.", WordingScope.LST),
    ],
)
def test_forbidden_wording_is_caught(text: str, scope: WordingScope) -> None:
    assert check_wording(text, {scope})


def test_negated_terms_are_allowed() -> None:
    assert check_wording("LST is not air temperature.", {WordingScope.LST}) == []
    assert check_wording("This is never an official warning.", {WordingScope.FORECAST}) == []


def test_due_to_is_fine_outside_driver_text() -> None:
    text = "Payback unavailable due to missing tariff."
    assert check_wording(text, {WordingScope.LST, WordingScope.FORECAST}) == []
