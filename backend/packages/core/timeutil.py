"""Clock access behind one function so tests can freeze time."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

__all__ = ["set_clock", "today", "utc_now"]

_clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def utc_now() -> datetime:
    """Current UTC time (timezone-aware)."""
    return _clock()


def today() -> date:
    return utc_now().date()


def set_clock(clock: Callable[[], datetime] | None) -> None:
    """Replace the clock (tests). ``None`` restores the real clock."""
    global _clock
    _clock = clock or (lambda: datetime.now(UTC))
