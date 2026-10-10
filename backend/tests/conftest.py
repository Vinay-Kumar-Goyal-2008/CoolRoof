"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from packages.core.params import ParamRegistry, load_params
from packages.core.settings import AppSettings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MINI_CITY = BACKEND_ROOT / "tests" / "fixtures" / "mini_city"


@pytest.fixture(scope="session")
def params() -> ParamRegistry:
    """The real default parameter registry."""
    return load_params()


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    """Local-runtime settings pointing at a throwaway data directory."""
    return AppSettings(data_dir=tmp_path / "data", _env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def mini_city_dir() -> Path:
    return MINI_CITY


@pytest.fixture(autouse=True)
def _reset_clock() -> Iterator[None]:
    from packages.core.timeutil import set_clock

    yield
    set_clock(None)
