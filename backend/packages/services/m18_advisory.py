"""M18+19 Public awareness advisories (bilingual, approval workflow) and text-to-speech.

1. **Compose** deterministically from slots (ward, level/source, validity) plus 1–3 whitelisted
   advice lines from ``rules/<v>/advice.json``. EN and HI.
2. **Optional rewriter** (LLM tone pass): accepted only if every number is grounded in the slots, the
   ward name survives and, for forecast items, the "forecast signal, not an official warning" label
   is kept. Otherwise the template text stays.
3. **Workflow** ``draft → approved → published → expired | withdrawn``; planner/admin approves,
   optionally by a second person. Forecast-based advisories default to ``staff`` audience.
4. **TTS**: English → Deepgram, Hindi → Polly (stub offline); cached by content hash; daily cap;
   a provider failure publishes text only.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.adapters.blobstore import BlobStore
from packages.adapters.docstore import DocStore, Table
from packages.adapters.tts import AudioResult, LanguageRoutedTTS
from packages.core.enums import Language
from packages.core.errors import (
    ConflictError,
    CoolRoofError,
    ForbiddenError,
    InputValidationError,
    NotFoundError,
    ThrottledError,
)
from packages.core.grounding import check_grounding
from packages.core.ids import new_uuid
from packages.core.logging import get_logger
from packages.core.timeutil import utc_now
from packages.pipeline.m43_heatdome import DISCLAIMER_EN, DISCLAIMER_HI
from packages.services.m37_alerts import AlertHub

__all__ = ["AdvisoryService", "load_advice"]

_log = get_logger("advisory")
ADVISORY_TYPES = ("heatwave_relay", "heatdome_forecast", "exam_event")
Rewriter = Callable[[str, str], str]


def load_advice(rules_dir: Path, version: str) -> dict[str, Any]:
    advice: dict[str, Any] = json.loads(
        (rules_dir / version / "advice.json").read_text(encoding="utf-8")
    )
    return advice


def _parse(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=utc_now().tzinfo)


def normalise_for_tts(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class AdvisoryService:
    def __init__(
        self,
        docs: DocStore,
        blobs: BlobStore,
        tts: LanguageRoutedTTS,
        hub: AlertHub,
        advice: dict[str, Any],
        *,
        two_person_rule: bool = False,
        tts_daily_cap: int = 200,
        rewriter: Rewriter | None = None,
    ) -> None:
        self._docs, self._blobs, self._tts, self._hub = docs, blobs, tts, hub
        self._advice = advice
        self._two_person = two_person_rule
        self._cap = tts_daily_cap
        self._rewriter = rewriter

    # ------------------------------------------------------------------ compose
    def compose(
        self,
        *,
        advisory_type: str,
        ward_name: dict[str, str],
        valid_until: str,
        level: str | None = None,
        issued_by: str | None = None,
        risk: str | None = None,
        has_cooling_point: bool = False,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Texts per language and the source slots they were built from."""
        if advisory_type not in ADVISORY_TYPES:
            raise InputValidationError(f"type must be one of {ADVISORY_TYPES}")
        end = _parse(valid_until)
        slots: dict[str, Any] = {
            "ward": ward_name,
            "valid_until": end.date().isoformat(),
            "day": end.day,
            "month": end.month,
            "year": end.year,
        }
        lines = list(self._advice["by_type"][advisory_type])
        if has_cooling_point and "cooling_point" not in lines:
            lines.append("cooling_point")
        lines = lines[:3]
        slots["advice_keys"] = lines
        forecast_based = advisory_type == "heatdome_forecast"
        if forecast_based:
            slots["risk"] = risk
            head = {
                "en": f"Heat advisory for {{ward}}: heat-dome {risk} level, {DISCLAIMER_EN}.",
                "hi": f"{{ward}} के लिए गर्मी की सलाह: हीट-डोम स्तर {risk}, {DISCLAIMER_HI}।",
            }
        else:
            slots["level"], slots["issued_by"] = level, issued_by
            head = {
                "en": f"Heat advisory for {{ward}}: {issued_by} has issued a {level} heatwave warning.",
                "hi": f"{{ward}} के लिए गर्मी की सलाह: {issued_by} ने {level} हीटवेव चेतावनी जारी की है।",
            }
        months_en = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        texts = {}
        for lang in ("en", "hi"):
            until = (
                f"Valid until {end.day} {months_en[end.month - 1]} {end.year}."
                if lang == "en"
                else f"{end.day}/{end.month}/{end.year} तक मान्य।"
            )
            advice = " ".join(self._advice["lines"][k][lang] for k in lines)
            texts[lang] = f"{head[lang].format(ward=ward_name[lang])} {until} {advice}"
        if self._rewriter is not None:
            texts = {
                lang: self._accept_rewrite(t, lang, slots, forecast_based)
                for lang, t in texts.items()
            }
        return texts, slots

    def _accept_rewrite(
        self, original: str, lang: str, slots: dict[str, Any], forecast: bool
    ) -> str:
        assert self._rewriter is not None
        try:
            candidate = self._rewriter(original, lang)
        except Exception:  # LLM unavailable: keep the template
            return original
        allowed = [slots["day"], slots["month"], slots["year"]]
        grounded = check_grounding(candidate, slots, allowed=allowed).grounded
        keeps_ward = slots["ward"][lang] in candidate
        keeps_label = (
            (DISCLAIMER_EN if lang == "en" else DISCLAIMER_HI) in candidate if forecast else True
        )
        if grounded and keeps_ward and keeps_label:
            return candidate
        _log.warning("advisory_rewrite_rejected", lang=lang, grounded=grounded)
        return original

    # ------------------------------------------------------------------ workflow
    def create(
        self,
        *,
        city: str,
        ward_id: str | None,
        advisory_type: str,
        texts: dict[str, str],
        slots: dict[str, Any],
        valid_until: str,
        audience: str | None = None,
        created_by: str,
        auto_info: bool = False,
    ) -> dict[str, Any]:
        forecast_based = advisory_type == "heatdome_forecast"
        audience = audience or ("staff" if forecast_based else "public")
        if forecast_based and audience == "public" and DISCLAIMER_EN not in texts["en"]:
            raise InputValidationError(
                "forecast-based public text must say it is a forecast signal"
            )
        doc: dict[str, Any] = {
            "advisory_id": new_uuid(),
            "city": city,
            "ward_id": ward_id,
            "type": advisory_type,
            "audience": audience,
            "status": "auto_info" if (auto_info and audience == "staff") else "draft",
            "texts": texts,
            "slots": slots,
            "valid_until": _parse(valid_until).isoformat(),
            "created_by": created_by,
            "created_at": utc_now().isoformat(),
            "approvals": [],
            "audio": {},
            "basis": "forecast_signal" if forecast_based else "official_warning",
        }
        self._docs.put(Table.ADVISORIES, f"city#{city}", doc["advisory_id"], doc)
        return doc

    def get(self, city: str, advisory_id: str) -> dict[str, Any]:
        doc = self._docs.get(Table.ADVISORIES, f"city#{city}", advisory_id)
        if doc is None:
            raise NotFoundError(f"advisory '{advisory_id}' not found")
        if (
            doc["status"] in ("approved", "published", "auto_info")
            and _parse(doc["valid_until"]) <= utc_now()
        ):
            doc["status"] = "expired"
            self._docs.put(Table.ADVISORIES, f"city#{city}", advisory_id, doc)
        return doc

    def list_advisories(self, city: str, status: str | None = None) -> list[dict[str, Any]]:
        rows = [
            self.get(city, r["advisory_id"])
            for r in self._docs.query(Table.ADVISORIES, f"city#{city}")
        ]
        return [r for r in rows if status is None or r["status"] == status]

    def approve(self, city: str, advisory_id: str, actor: str, role: str) -> dict[str, Any]:
        if role not in ("planner", "admin"):
            raise ForbiddenError("only a planner or admin can approve an advisory")
        doc = self.get(city, advisory_id)
        if doc["status"] != "draft":
            raise ConflictError(f"advisory is already {doc['status']}")
        if self._two_person and actor == doc["created_by"]:
            raise ConflictError("the two-person rule needs a different approver")
        doc["approvals"].append({"by": actor, "role": role, "at": utc_now().isoformat()})
        doc["status"] = "approved"
        self._docs.put(Table.ADVISORIES, f"city#{city}", advisory_id, doc)
        return doc

    def publish(self, city: str, advisory_id: str, actor: str) -> dict[str, Any]:
        doc = self.get(city, advisory_id)
        if doc["status"] != "approved":
            raise ConflictError("only an approved advisory can be published")
        alert = self._hub.raise_alert(
            alert_type=f"advisory_{doc['type']}",
            city=city,
            audience=doc["audience"],
            severity="medium",
            texts=doc["texts"],
            valid_until=doc["valid_until"],
            ward_id=doc["ward_id"],
            dedupe_key=doc["advisory_id"],
            source_ref=f"advisory:{advisory_id}",
            actor=actor,
        )
        self._hub.approve(city, alert["alert_id"], actor)
        sent = self._hub.send(city, alert["alert_id"], actor)
        doc["status"] = "published"
        doc["alert_id"] = sent["alert_id"]
        self._docs.put(Table.ADVISORIES, f"city#{city}", advisory_id, doc)
        return doc

    def withdraw(self, city: str, advisory_id: str, actor: str) -> dict[str, Any]:
        doc = self.get(city, advisory_id)
        doc["status"] = "withdrawn"
        doc.setdefault("audit", []).append(
            {"by": actor, "at": utc_now().isoformat(), "action": "withdrawn"}
        )
        self._docs.put(Table.ADVISORIES, f"city#{city}", advisory_id, doc)
        if doc.get("alert_id"):
            self._hub.withdraw(city, doc["alert_id"], actor)
        return doc

    @staticmethod
    def deliverable(doc: dict[str, Any], now: datetime | None = None) -> bool:
        """Unapproved, withdrawn or expired advisories are never delivered."""
        return doc["status"] in ("approved", "published", "auto_info") and _parse(
            doc["valid_until"]
        ) > (now or utc_now())

    # ------------------------------------------------------------------ TTS
    def _count_today(self) -> int:
        today = utc_now().date().isoformat()
        doc = self._docs.get(Table.CACHE, f"tts#{today}")
        return int(doc["count"]) if doc else 0

    def _bump(self) -> None:
        today = utc_now().date().isoformat()
        self._docs.put(
            Table.CACHE, f"tts#{today}", "-", {"count": self._count_today() + 1}, ttl_s=3 * 86400
        )

    def audio(self, city: str, advisory_id: str, lang: str) -> dict[str, Any]:
        """Audio for an approved advisory, or ``{"audio": None}`` (text only) if TTS fails."""
        if lang not in ("en", "hi"):
            raise InputValidationError("lang must be en or hi")
        doc = self.get(city, advisory_id)
        if not self.deliverable(doc):
            raise ConflictError("audio is only produced for approved, unexpired advisories")
        text = normalise_for_tts(doc["texts"][lang])
        language = Language(lang)
        provider = self._tts.provider_for(language)
        key_src = f"{provider.name}|{lang}|{text}"
        key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
        for ext in ("mp3", "wav"):
            blob_key = f"tts/{key}.{ext}"
            if self._blobs.exists(blob_key):
                return {"audio": blob_key, "cached": True, "provider": provider.name, "text": text}
        if self._count_today() >= self._cap:
            raise ThrottledError("daily speech-synthesis limit reached; showing text only")
        try:
            result: AudioResult = self._tts.synthesize(text, language)
        except CoolRoofError as exc:
            _log.warning("tts_failed", provider=provider.name, error=exc.message)
            return {"audio": None, "fallback": "text_only", "provider": provider.name, "text": text}
        blob_key = f"tts/{key}.{result.extension}"
        self._blobs.put(blob_key, result.audio, content_type=result.content_type)
        self._bump()
        return {"audio": blob_key, "cached": False, "provider": result.provider, "text": text}
