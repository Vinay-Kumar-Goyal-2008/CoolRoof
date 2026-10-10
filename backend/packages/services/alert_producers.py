"""Producers that turn module outputs into M37 alerts.

Staff-only information items (fire candidates, forecast signals, degradation transitions, habitat
warnings) are ``auto_info``; nothing public is created here. Public items come from approved
advisories (M18+19) or confirmed incidents (M22).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from packages.adapters.docstore import DocStore, Table
from packages.core.enums import DegradationSignal
from packages.core.timeutil import utc_now
from packages.pipeline.m22_fire import FireEvent
from packages.pipeline.m24_degradation import UnitTrends
from packages.pipeline.m43_heatdome import DISCLAIMER_EN, DISCLAIMER_HI
from packages.services.m37_alerts import AlertHub

__all__ = [
    "degradation_transitions",
    "produce_fire_alerts",
    "produce_habitat_alerts",
    "produce_heatdome_alert",
    "produce_transition_alerts",
]

_SIGNAL_RANK = {
    DegradationSignal.NOT_APPLICABLE.value: -1,
    DegradationSignal.INSUFFICIENT_DATA.value: -1,
    DegradationSignal.NONE.value: 0,
    DegradationSignal.WEAK.value: 1,
    DegradationSignal.MODERATE.value: 2,
    DegradationSignal.STRONG.value: 3,
}


def _expiry(hours: int = 24) -> str:
    return (utc_now() + timedelta(hours=hours)).isoformat()


def produce_fire_alerts(hub: AlertHub, city: str, events: list[FireEvent]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        if not e.alert:
            continue
        where = e.ward_id or e.protected_area_id or "the city area"
        reasons = ", ".join(r.replace("_", " ") for r in e.alert_reasons)
        out.append(
            hub.raise_alert(
                alert_type="satellite_fire",
                city=city,
                audience="staff",
                severity=e.severity or "low",
                texts={
                    "en": f"Satellite vegetation-fire detection near {where} ({reasons}); last satellite pass {e.acq_date} {e.acq_time} UTC. Not real time.",
                    "hi": f"{where} के पास उपग्रह से वनस्पति आग का पता चला ({reasons}); अंतिम उपग्रह गुज़रना {e.acq_date} {e.acq_time} UTC। वास्तविक समय नहीं।",
                },
                valid_until=_expiry(24),
                ward_id=e.ward_id,
                dedupe_key=e.event_id,
                source_ref=f"fire:{e.event_id}",
                auto_info=True,
            )
        )
    return out


def produce_heatdome_alert(
    hub: AlertHub, city: str, forecast: dict[str, Any]
) -> dict[str, Any] | None:
    if forecast.get("risk") not in ("elevated", "high"):
        return None
    first = forecast.get("first_date") or "the coming days"
    return hub.raise_alert(
        alert_type="heatdome_forecast",
        city=city,
        audience="staff",
        severity="high" if forecast["risk"] == "high" else "medium",
        texts={
            "en": f"Heat-dome signal, risk {forecast['risk']}, from {first} ({DISCLAIMER_EN}). Official IMD warnings take precedence.",
            "hi": f"हीट-डोम संकेत, जोखिम {forecast['risk']}, {first} से ({DISCLAIMER_HI})। आधिकारिक IMD चेतावनी को प्राथमिकता दें।",
        },
        valid_until=_expiry(48),
        dedupe_key=str(forecast.get("issued_at")),
        source_ref="forecast:heatdome",
        auto_info=True,
    )


def degradation_transitions(
    docs: DocStore, city: str, trends: dict[str, UnitTrends]
) -> list[dict[str, str]]:
    """Wards whose signal rose ≥ 1 class vs the previous stored run (call before persisting)."""
    out = []
    for uid, t in trends.items():
        if t.unit_kind != "ward":
            continue
        old = docs.get(Table.ENVIRONMENT, f"soil#{city}", uid)
        if old is None:
            continue
        before, after = old["degradation_signal"], t.signal.value
        if (
            _SIGNAL_RANK.get(after, -1) >= 0
            and _SIGNAL_RANK.get(after, -1) - _SIGNAL_RANK.get(before, -1) >= 1
            and _SIGNAL_RANK.get(before, -1) >= 0
        ):
            out.append({"ward_id": uid, "from": before, "to": after})
    return out


def produce_transition_alerts(
    hub: AlertHub, city: str, transitions: list[dict[str, str]]
) -> list[dict[str, Any]]:
    return [
        hub.raise_alert(
            alert_type="degradation_transition",
            city=city,
            audience="staff",
            severity="low",
            texts={
                "en": f"Land-degradation indicator for ward {t['ward_id']} rose from {t['from']} to {t['to']} (indicator, not diagnosis). Planner review only.",
                "hi": f"वार्ड {t['ward_id']} का भूमि क्षरण संकेतक {t['from']} से {t['to']} हुआ (संकेतक, निदान नहीं)। केवल योजनाकार समीक्षा।",
            },
            valid_until=_expiry(24 * 14),
            ward_id=t["ward_id"],
            dedupe_key=f"{t['from']}>{t['to']}",
            auto_info=True,
        )
        for t in transitions
    ]


def produce_habitat_alerts(
    hub: AlertHub, city: str, areas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out = []
    for pa in areas:
        for w in pa.get("warnings", []):
            event_driven = w["code"].startswith("PA_FIRE")
            out.append(
                hub.raise_alert(
                    alert_type=w["code"].lower(),
                    city=city,
                    audience="staff",
                    severity="medium" if event_driven else "low",
                    texts={
                        "en": f"{w['message']}. Habitat pressure indicator, unverified — not a measured biodiversity loss.",
                    },
                    valid_until=_expiry(24 * (3 if event_driven else 30)),
                    dedupe_key=f"{pa['pa_id']}|{w['code']}|{w.get('count', '')}",
                    source_ref=f"protected_area:{pa['pa_id']}",
                    auto_info=True,
                )
            )
    return out
