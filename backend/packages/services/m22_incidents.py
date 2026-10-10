"""M22 incident path: staff-logged structure fires (normal fires, not satellite detections).

``POST /fire/incidents`` logs a ``structure_fire_reported``; a *second* staff member confirms it
(``structure_fire_confirmed``). A nearby satellite urban-thermal candidate is *linked* to the
incident but never auto-confirms it. A public alert is only drafted for confirmed incidents and
needs M18+19/M37 approval. Each incident is attached to its ward with nearby hospitals and schools.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from packages.adapters.docstore import DocStore, Table
from packages.core.enums import FireClass, IncidentClass
from packages.core.errors import ConflictError, InputValidationError, NotFoundError
from packages.core.ids import new_uuid
from packages.core.params import ParamRegistry
from packages.core.timeutil import utc_now
from packages.services.m37_alerts import AlertHub

__all__ = ["IncidentService"]

LINK_RADIUS_M = 1000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


class IncidentService:
    def __init__(
        self,
        docs: DocStore,
        hub: AlertHub,
        params: ParamRegistry,
        *,
        facilities: list[dict[str, Any]] | None = None,
        ward_lookup: Any = None,
    ) -> None:
        self._docs, self._hub, self._params = docs, hub, params
        self._facilities = facilities or []  # [{kind, name, lat, lon}]
        self._ward_lookup = ward_lookup  # callable (lat, lon) -> ward_id | None

    def _nearby(self, lat: float, lon: float) -> dict[str, list[dict[str, Any]]]:
        radius = self._params.require_float("P-COVER")
        out: dict[str, list[dict[str, Any]]] = {"hospitals": [], "schools": []}
        for f in self._facilities:
            d = _haversine_m(lat, lon, f["lat"], f["lon"])
            if d <= radius and f["kind"] in ("hospital", "school"):
                out["hospitals" if f["kind"] == "hospital" else "schools"].append(
                    {"name": f["name"], "distance_m": round(d)}
                )
        return out

    def report(
        self,
        city: str,
        *,
        lat: float,
        lon: float,
        occurred_at: str,
        kind: str,
        source: str,
        notes: str,
        reporter: str,
        satellite_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise InputValidationError("lat/lon out of range")
        when = occurred_at
        linked = [
            e["event_id"]
            for e in (satellite_events or [])
            if e.get("fire_class") == FireClass.URBAN_THERMAL_ANOMALY_CANDIDATE.value
            and _haversine_m(lat, lon, e["lat"], e["lon"]) <= LINK_RADIUS_M
            and e.get("acq_date") == when[:10]
        ]
        incident = {
            "incident_id": new_uuid(),
            "city": city,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "occurred_at": when,
            "type": kind,
            "source": source,
            "notes": notes[:500],
            "status": IncidentClass.STRUCTURE_FIRE_REPORTED.value,
            "ward_id": self._ward_lookup(lat, lon) if self._ward_lookup else None,
            "nearby": self._nearby(lat, lon),
            "linked_satellite_candidates": linked,
            "reported_by": reporter,
            "confirmed_by": None,
            "created_at": utc_now().isoformat(),
        }
        self._docs.put(
            Table.ENVIRONMENT, f"incident#{city}", f"{when}#{incident['incident_id']}", incident
        )
        return incident

    def _find(self, city: str, incident_id: str) -> dict[str, Any]:
        for row in self._docs.query(
            Table.ENVIRONMENT, f"incident#{city}", descending=True, limit=500
        ):
            if row["incident_id"] == incident_id:
                return row
        raise NotFoundError(f"incident '{incident_id}' not found")

    def confirm(self, city: str, incident_id: str, confirmer: str) -> dict[str, Any]:
        inc = self._find(city, incident_id)
        if inc["status"] == IncidentClass.STRUCTURE_FIRE_CONFIRMED.value:
            raise ConflictError("incident already confirmed")
        if confirmer == inc["reported_by"]:
            raise ConflictError("a second staff member must confirm the incident")
        inc["status"] = IncidentClass.STRUCTURE_FIRE_CONFIRMED.value
        inc["confirmed_by"] = confirmer
        inc["confirmed_at"] = utc_now().isoformat()
        self._docs.put(
            Table.ENVIRONMENT, f"incident#{city}", f"{inc['occurred_at']}#{incident_id}", inc
        )
        # Public alerts only for confirmed incidents, as a *draft* needing approval.
        near = inc["nearby"]
        hosp = near["hospitals"][0]["name"] if near["hospitals"] else None
        extra_en = f" Nearest hospital: {hosp}." if hosp else ""
        extra_hi = f" निकटतम अस्पताल: {hosp}।" if hosp else ""
        alert = self._hub.raise_alert(
            alert_type="structure_fire_confirmed",
            city=city,
            audience="public",
            severity="high",
            texts={
                "en": f"A structure fire has been confirmed near ward {inc['ward_id'] or 'unknown'}. Follow fire-service instructions.{extra_en}",
                "hi": f"वार्ड {inc['ward_id'] or 'अज्ञात'} के पास इमारत में आग की पुष्टि हुई है। दमकल सेवा के निर्देशों का पालन करें।{extra_hi}",
            },
            valid_until=(utc_now() + timedelta(hours=12)).isoformat(),
            ward_id=inc["ward_id"],
            dedupe_key=incident_id,
            source_ref=f"incident:{incident_id}",
            actor=confirmer,
        )
        inc["public_alert_id"] = alert["alert_id"]
        return inc

    def list_incidents(self, city: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._docs.query(Table.ENVIRONMENT, f"incident#{city}", descending=True, limit=limit)

    def count_30d(self, city: str, ward_id: str) -> int:
        since = (utc_now() - timedelta(days=30)).isoformat()
        return sum(
            1
            for i in self.list_incidents(city, 500)
            if i["ward_id"] == ward_id and i["occurred_at"] >= since
        )
