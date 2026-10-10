"""Official heatwave warnings (manual IMD entries) and the current heat signal for a city.

Official warnings always take precedence over the M43 forecast signal. They are entered by
staff (``POST /admin/official-warnings``) and stored in the DocStore with a validity window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from packages.adapters.docstore import DocStore, Table
from packages.core.errors import InputValidationError
from packages.core.ids import new_uuid
from packages.core.timeutil import utc_now

__all__ = ["OfficialWarnings", "Signals", "current_signals"]

LEVELS = ("yellow", "orange", "red")


def _parse(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=utc_now().tzinfo)


class OfficialWarnings:
    def __init__(self, docs: DocStore) -> None:
        self._docs = docs

    def add(
        self,
        city: str,
        *,
        level: str,
        issued_by: str,
        valid_from: str,
        valid_until: str,
        text: str,
        source_url: str | None = None,
        entered_by: str = "staff",
    ) -> dict[str, Any]:
        if level not in LEVELS:
            raise InputValidationError(f"level must be one of {LEVELS}")
        start, end = _parse(valid_from), _parse(valid_until)
        if end <= start:
            raise InputValidationError("valid_until must be after valid_from")
        doc = {
            "warning_id": new_uuid(),
            "city": city,
            "level": level,
            "issued_by": issued_by,
            "valid_from": start.isoformat(),
            "valid_until": end.isoformat(),
            "text": text,
            "source_url": source_url,
            "entered_by": entered_by,
            "entered_at": utc_now().isoformat(),
            "kind": "official_warning_manual_entry",
        }
        self._docs.put(
            Table.CONFIG, f"warning#{city}", f"{start.isoformat()}#{doc['warning_id']}", doc
        )
        return doc

    def active(self, city: str, now: datetime | None = None) -> dict[str, Any] | None:
        """Highest-level warning currently in force (None if there is none)."""
        now = now or utc_now()
        rows = self._docs.query(Table.CONFIG, f"warning#{city}", descending=True, limit=20)
        live = [r for r in rows if _parse(r["valid_from"]) <= now < _parse(r["valid_until"])]
        if not live:
            return None
        return max(live, key=lambda r: LEVELS.index(r["level"]))

    def history(self, city: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._docs.query(Table.CONFIG, f"warning#{city}", descending=True, limit=limit)


@dataclass(frozen=True)
class Signals:
    official: dict[str, Any] | None
    forecast_risk: str
    forecast: dict[str, Any] | None

    @property
    def active(self) -> bool:
        return self.official is not None or self.forecast_risk in ("elevated", "high")

    def to_dict(self) -> dict[str, Any]:
        return {
            "official_warning": self.official,
            "forecast_risk": self.forecast_risk,
            "active": self.active,
            "precedence": "official warning first, then forecast signal",
        }


def current_signals(docs: DocStore, city: str, forecast: dict[str, Any] | None) -> Signals:
    return Signals(
        OfficialWarnings(docs).active(city),
        str((forecast or {}).get("risk", "unavailable")),
        forecast,
    )
