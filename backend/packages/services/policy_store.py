"""Policy-as-data repository (M29, M30+31, M35+36).

Policy records (subsidy, top-up, tariff, net metering, checklist, IMD criteria)
live in the DocStore under ``policy#<type>#<state>#<discom>`` with the
effective date as sort key. Code never hard-codes their contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from packages.adapters.docstore import DocStore, Table
from packages.core.ids import record_hash

__all__ = ["PolicyRecord", "PolicyStore", "PolicyType", "policy_key"]

NATIONAL = "ALL"


class PolicyType(StrEnum):
    SUBSIDY = "subsidy"
    SUBSIDY_TOPUP = "subsidy_topup"
    TARIFF = "tariff"
    NETMETERING = "netmetering"
    CHECKLIST = "checklist"
    IMD_HEATWAVE_CRITERIA = "imd_heatwave_criteria"


def policy_key(ptype: PolicyType, state: str = NATIONAL, discom: str = NATIONAL) -> str:
    return f"policy#{ptype.value}#{state}#{discom}"


@dataclass(frozen=True)
class PolicyRecord:
    """A stored policy document plus its identity."""

    ptype: PolicyType
    state: str
    discom: str
    effective_date: str
    doc: dict[str, Any]

    @property
    def key(self) -> str:
        return policy_key(self.ptype, self.state, self.discom)

    @property
    def version(self) -> str:
        return f"{self.ptype.value}:{self.state}:{self.discom}:{self.effective_date}"

    @property
    def hash(self) -> str:
        return record_hash(self.doc)

    @property
    def reviewed_on(self) -> date | None:
        raw = self.doc.get("reviewed_on")
        return date.fromisoformat(raw) if raw else None

    @property
    def is_synthetic(self) -> bool:
        return bool(self.doc.get("synthetic"))

    def age_days(self, today: date) -> int | None:
        reviewed = self.reviewed_on
        return (today - reviewed).days if reviewed else None


class PolicyStore:
    """Read/write policy records with effective-date lookup."""

    def __init__(self, docstore: DocStore) -> None:
        self._db = docstore

    def put(self, ptype: PolicyType, doc: dict[str, Any]) -> PolicyRecord:
        state = str(doc.get("state", NATIONAL))
        discom = str(doc.get("discom", NATIONAL))
        effective = str(doc["effective_date"])
        self._db.put(Table.POLICY, policy_key(ptype, state, discom), effective, doc)
        return PolicyRecord(ptype, state, discom, effective, doc)

    def get(
        self,
        ptype: PolicyType,
        *,
        state: str = NATIONAL,
        discom: str = NATIONAL,
        on: date | None = None,
    ) -> PolicyRecord | None:
        """The record in force on ``on`` (latest effective date ≤ on) for exactly this key."""
        pk = policy_key(ptype, state, discom)
        rows = self._db.query(
            Table.POLICY, pk, sk_lte=on.isoformat() if on else None, descending=True, limit=1
        )
        if not rows:
            return None
        doc = rows[0]
        return PolicyRecord(ptype, state, discom, str(doc["effective_date"]), doc)

    def resolve(
        self,
        ptype: PolicyType,
        *,
        state: str,
        discom: str,
        on: date | None = None,
    ) -> tuple[PolicyRecord | None, str]:
        """Most specific record: state+DISCOM → state → national. Returns (record, level)."""
        for level, (st, dc) in (
            ("state+discom", (state, discom)),
            ("state", (state, NATIONAL)),
            ("national", (NATIONAL, NATIONAL)),
        ):
            record = self.get(ptype, state=st, discom=dc, on=on)
            if record is not None:
                return record, level
        return None, "none"
