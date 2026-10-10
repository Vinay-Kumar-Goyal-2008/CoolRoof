"""Load seed policy records (``seed/policy/*.json``) into the configured DocStore.

A tariff file may embed its settlement terms; they are stored as a separate
``netmetering`` record, matching the spec's two record types.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.adapters.registry import build_adapters
from packages.core.settings import AppSettings, get_settings
from packages.services.policy_store import PolicyStore, PolicyType


def seed_policies(store: PolicyStore, seed_dir: Path) -> list[str]:
    """Write every seed record; returns the stored record versions."""
    stored: list[str] = []
    for path in sorted((seed_dir / "policy").glob("*.json")):
        doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        ptype = PolicyType(doc["type"])
        settlement = doc.pop("settlement", None)
        stored.append(store.put(ptype, doc).version)
        if settlement:
            settlement_doc = {
                **settlement,
                "type": PolicyType.NETMETERING.value,
                "state": doc["state"],
                "discom": doc["discom"],
                "effective_date": doc["effective_date"],
                "reviewed_on": doc.get("reviewed_on"),
                "synthetic": doc.get("synthetic", False),
            }
            stored.append(store.put(PolicyType.NETMETERING, settlement_doc).version)
    return stored


def main(settings: AppSettings | None = None) -> None:
    settings = settings or get_settings()
    adapters = build_adapters(settings)
    for version in seed_policies(PolicyStore(adapters.docstore), settings.seed_dir):
        print(f"seeded {version}")


if __name__ == "__main__":
    main()
