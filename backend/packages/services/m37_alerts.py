"""M37 Alerts and notifications: one hub for every producer (fire, forecast, advisories, trends).

* Audiences: ``staff`` (planners, emergency contacts) and ``public`` (opt-in). Public items must be
  ``approved``/``published`` first; staff information items may be ``auto_info``.
* Dedupe by deterministic ``alert_id``; rate limit ``P-ALERT-RATE`` (severity escalation passes);
  ``valid_until`` enforced at send and read time; one publish per language; full audit trail.
* Subscriptions store only a salted hash of the address (SNS holds the real endpoint on AWS).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from packages.adapters.docstore import DocStore, Table
from packages.adapters.notifier import Notifier
from packages.core.errors import ConflictError, InputValidationError, NotFoundError
from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.core.timeutil import utc_now

__all__ = ["SEVERITIES", "AlertHub", "AlertStatus"]

_log = get_logger("alerts")
_NAMESPACE = uuid.UUID("5d0f2a1e-0b7a-4c3e-9a55-3f6d1c9d7a10")
SEVERITIES = ("info", "low", "medium", "high")
LANGS = ("en", "hi")


class AlertStatus:
    DRAFT = "draft"
    APPROVED = "approved"
    AUTO_INFO = "auto_info"
    PUBLISHED = "published"
    SENT = "sent"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


_DELIVERABLE = {AlertStatus.APPROVED, AlertStatus.AUTO_INFO, AlertStatus.PUBLISHED}


def _parse(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=utc_now().tzinfo)


class AlertHub:
    def __init__(
        self, docs: DocStore, notifier: Notifier, params: ParamRegistry, *, salt: str = "coolroof"
    ) -> None:
        self._docs = docs
        self._notifier = notifier
        self._params = params
        self._salt = salt

    # ------------------------------------------------------------------ create
    def raise_alert(
        self,
        *,
        alert_type: str,
        city: str,
        audience: str,
        severity: str,
        texts: dict[str, str],
        valid_until: str,
        ward_id: str | None = None,
        dedupe_key: str = "",
        source_ref: str | None = None,
        auto_info: bool = False,
        actor: str = "system",
    ) -> dict[str, Any]:
        """Create (and, for staff info items, send) an alert. Returns the stored alert."""
        if audience not in ("staff", "public"):
            raise InputValidationError("audience must be staff or public")
        if severity not in SEVERITIES:
            raise InputValidationError(f"severity must be one of {SEVERITIES}")
        if set(texts) - set(LANGS) or "en" not in texts:
            raise InputValidationError("texts need an 'en' entry; optional 'hi'")
        if audience == "public" and auto_info:
            raise InputValidationError("public alerts cannot be auto_info; they need approval")
        alert_id = str(uuid.uuid5(_NAMESPACE, f"{alert_type}|{city}|{ward_id}|{dedupe_key}"))
        now = utc_now()
        doc = {
            "alert_id": alert_id,
            "type": alert_type,
            "city": city,
            "ward_id": ward_id,
            "audience": audience,
            "severity": severity,
            "texts": texts,
            "valid_until": _parse(valid_until).isoformat(),
            "source_ref": source_ref,
            "status": AlertStatus.AUTO_INFO if auto_info else AlertStatus.DRAFT,
            "created_at": now.isoformat(),
            "deliveries": [],
            "audit": [{"ts": now.isoformat(), "actor": actor, "action": "created"}],
        }
        stored = self._docs.put(Table.ALERTS, f"city#{city}", alert_id, doc, if_absent=True)
        if not stored:  # duplicate producer run → idempotent
            return self.get(city, alert_id)
        if doc["status"] == AlertStatus.AUTO_INFO:
            return self.send(city, alert_id, actor=actor)
        return doc

    # ------------------------------------------------------------------ workflow
    def get(self, city: str, alert_id: str) -> dict[str, Any]:
        doc = self._docs.get(Table.ALERTS, f"city#{city}", alert_id)
        if doc is None:
            raise NotFoundError(f"alert '{alert_id}' not found")
        return doc

    def _save(self, doc: dict[str, Any], action: str, actor: str) -> dict[str, Any]:
        doc["audit"].append({"ts": utc_now().isoformat(), "actor": actor, "action": action})
        self._docs.put(Table.ALERTS, f"city#{doc['city']}", doc["alert_id"], doc)
        return doc

    def approve(self, city: str, alert_id: str, actor: str) -> dict[str, Any]:
        doc = self.get(city, alert_id)
        if doc["status"] != AlertStatus.DRAFT:
            raise ConflictError(f"alert is already {doc['status']}")
        if self._is_expired(doc):
            raise ConflictError("alert has expired")
        doc["status"] = AlertStatus.APPROVED
        doc["approved_by"] = actor
        return self._save(doc, "approved", actor)

    def withdraw(self, city: str, alert_id: str, actor: str) -> dict[str, Any]:
        doc = self.get(city, alert_id)
        doc["status"] = AlertStatus.WITHDRAWN
        return self._save(doc, "withdrawn", actor)

    @staticmethod
    def _is_expired(doc: dict[str, Any], now: datetime | None = None) -> bool:
        return _parse(doc["valid_until"]) <= (now or utc_now())

    # ------------------------------------------------------------------ send
    def _rate_limited(self, doc: dict[str, Any]) -> bool:
        cfg = self._params.require("P-ALERT-RATE")
        now = utc_now()
        recent = [
            a
            for a in self._docs.query(
                Table.ALERTS, f"city#{doc['city']}", descending=True, limit=200
            )
            if a["status"] == AlertStatus.SENT and a["alert_id"] != doc["alert_id"]
        ]
        last_hour = [a for a in recent if (now - _parse(a["sent_at"])).total_seconds() < 3600]
        last_day = [
            a
            for a in recent
            if a.get("ward_id") == doc.get("ward_id")
            and (now - _parse(a["sent_at"])).total_seconds() < 86400
        ]
        if doc["ward_id"] and len(last_day) >= int(cfg["per_ward_per_day"]):
            return True
        return len(last_hour) >= int(cfg["per_city_per_hour"])

    def send(self, city: str, alert_id: str, actor: str = "system") -> dict[str, Any]:
        doc = self.get(city, alert_id)
        if doc["status"] not in _DELIVERABLE:
            raise ConflictError(
                f"alert is {doc['status']}: only approved or auto_info alerts are sent"
            )
        if self._is_expired(doc):
            doc["status"] = AlertStatus.EXPIRED
            return self._save(doc, "expired_before_send", actor)
        if self._rate_limited(doc) and doc["severity"] != "high":
            doc["status"] = AlertStatus.SUPPRESSED
            return self._save(doc, "suppressed_rate_limit", actor)
        topic = f"{city}-{doc['audience']}"
        for lang, text in doc["texts"].items():
            message_id = self._notifier.publish(
                topic,
                f"[{doc['severity']}] {doc['type']}",
                {"text": text, "valid_until": doc["valid_until"], "alert_id": alert_id},
                {
                    "ward_id": doc["ward_id"] or "ALL",
                    "language": lang,
                    "severity": doc["severity"],
                    "type": doc["type"],
                },
            )
            doc["deliveries"].append({"language": lang, "message_id": message_id, "topic": topic})
        doc["status"] = AlertStatus.SENT
        doc["sent_at"] = utc_now().isoformat()
        return self._save(doc, "sent", actor)

    # ------------------------------------------------------------------ read
    def active(
        self, city: str, ward_id: str | None = None, *, include_staff: bool = False
    ) -> list[dict[str, Any]]:
        """Alerts safe to show now: delivered, not expired, public (or staff for staff)."""
        now = utc_now()
        out = []
        for doc in self._docs.query(Table.ALERTS, f"city#{city}", descending=True, limit=200):
            if doc["status"] not in (
                AlertStatus.SENT,
                AlertStatus.PUBLISHED,
                AlertStatus.AUTO_INFO,
            ):
                continue
            if self._is_expired(doc, now):
                continue
            if doc["audience"] == "staff" and not include_staff:
                continue
            if ward_id and doc["ward_id"] not in (None, ward_id):
                continue
            out.append(doc)
        return out

    def drafts(self, city: str) -> list[dict[str, Any]]:
        return [
            d
            for d in self._docs.query(Table.ALERTS, f"city#{city}", descending=True, limit=200)
            if d["status"] == AlertStatus.DRAFT and not self._is_expired(d)
        ]

    # ------------------------------------------------------------------ subscriptions
    def _hash(self, address: str) -> str:
        return hashlib.sha256(f"{self._salt}|{address.strip().lower()}".encode()).hexdigest()

    def subscribe(
        self,
        city: str,
        *,
        channel: str,
        address: str,
        ward_ids: list[str] | None,
        languages: list[str],
    ) -> dict[str, Any]:
        if channel not in ("email", "sms"):
            raise InputValidationError("channel must be email or sms")
        if channel == "email" and "@" not in address:
            raise InputValidationError("invalid email address")
        if channel == "sms" and not address.lstrip("+").isdigit():
            raise InputValidationError("invalid phone number")
        if not languages or set(languages) - set(LANGS):
            raise InputValidationError("languages must be a subset of en, hi")
        sub_id = self._hash(f"{city}|{channel}|{address}")[:24]
        doc = {
            "subscription_id": sub_id,
            "city": city,
            "channel": channel,
            "address_hash": self._hash(address),
            "ward_ids": ward_ids or [],
            "languages": languages,
            "status": "pending_confirmation" if channel == "email" else "needs_sender_registration",
            "created_at": utc_now().isoformat(),
            "filter_policy": {
                "ward_id": [*(ward_ids or []), "ALL"] if ward_ids else ["ALL"],
                "language": languages,
            },
        }
        self._docs.put(Table.SUBSCRIPTIONS, f"city#{city}", sub_id, doc)
        return {k: v for k, v in doc.items() if k != "address_hash"}

    def unsubscribe(self, city: str, subscription_id: str) -> None:
        if self._docs.get(Table.SUBSCRIPTIONS, f"city#{city}", subscription_id) is None:
            raise NotFoundError("subscription not found")
        self._docs.delete(Table.SUBSCRIPTIONS, f"city#{city}", subscription_id)

    def matching_subscriptions(self, city: str, doc: dict[str, Any], language: str) -> list[str]:
        """Local mimic of SNS filter policies (used by tests and the outbox view)."""
        out = []
        for sub in self._docs.query(Table.SUBSCRIPTIONS, f"city#{city}"):
            ward_ok = not sub["ward_ids"] or doc["ward_id"] in (None, *sub["ward_ids"])
            if ward_ok and language in sub["languages"]:
                out.append(sub["subscription_id"])
        return out
