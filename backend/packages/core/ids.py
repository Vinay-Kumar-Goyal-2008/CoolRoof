"""Identifier generation (§4.4). Deterministic IDs are pure functions of their inputs."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import date, datetime
from typing import Any

__all__ = [
    "building_id",
    "canonical_json",
    "context_version",
    "fire_dedupe_key",
    "input_hash",
    "new_alert_id",
    "new_run_id",
    "new_session_id",
    "new_uuid",
    "record_hash",
]


def canonical_json(obj: Any) -> str:
    """Stable JSON (sorted keys, no whitespace) used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def building_id(dataset_id: str, geometry_wkb: bytes) -> str:
    """``building_id = roof_id = hash(dataset_id + geometry)`` — stable across runs."""
    digest = hashlib.sha256(dataset_id.encode("utf-8") + b"|" + geometry_wkb).hexdigest()
    return f"b_{digest[:20]}"


def input_hash(payload: Any) -> str:
    """Idempotency key for pure request handlers (e.g. M32)."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def record_hash(record: Any) -> str:
    """Hash of a policy or rules record, quoted in outputs and PDF footers."""
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()[:16]


def fire_dedupe_key(lat: float, lon: float, acq_date: str, acq_time: str, instrument: str) -> str:
    """``sha1(round(lat,4), round(lon,4), date, time, instrument)``."""
    raw = f"{round(lat, 4):.4f}|{round(lon, 4):.4f}|{acq_date}|{acq_time}|{instrument}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def new_session_id() -> str:
    """128-bit random session id."""
    return secrets.token_hex(16)


def new_uuid() -> str:
    return str(uuid.uuid4())


def new_alert_id() -> str:
    return new_uuid()


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(3)}"


def context_version(on: date | None = None) -> str:
    """Date-stamped context version, e.g. ``2026-10-10``."""
    return (on or date.today()).isoformat()
