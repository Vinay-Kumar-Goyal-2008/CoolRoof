from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

from packages.adapters.blobstore import LocalBlobStore
from packages.adapters.notifier import FileNotifier
from packages.adapters.registry import build_adapters
from packages.adapters.tts import DeepgramTTS, SilentWavStub
from packages.core.enums import Language
from packages.core.errors import NotFoundError
from packages.core.settings import AppSettings


def test_blobstore_round_trip_and_listing(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path)
    store.put("curated/mini/heat.parquet", b"abc")
    store.put_text("rules/v1/rules.json", "{}")
    assert store.get("curated/mini/heat.parquet") == b"abc"
    assert store.list("curated/") == ["curated/mini/heat.parquet"]
    assert Path(store.uri("rules/v1/rules.json")).is_file()


def test_blobstore_missing_key_and_path_escape(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "root")
    with pytest.raises(NotFoundError):
        store.get("nope")
    with pytest.raises(ValueError, match="escapes"):
        store.put("../outside.txt", b"x")


def test_file_notifier_writes_outbox(tmp_path: Path) -> None:
    notifier = FileNotifier(tmp_path)
    mid = notifier.publish("mini-staff", "Heat", {"text": "hello"}, {"ward_id": "W01"})
    [msg] = notifier.read_outbox("mini-staff")
    assert msg["message_id"] == mid
    assert msg["attributes"] == {"ward_id": "W01"}


def test_silent_stub_returns_valid_wav() -> None:
    audio = SilentWavStub().synthesize("नमस्ते", Language.HI)
    with wave.open(io.BytesIO(audio.audio)) as wav:
        assert wav.getnframes() > 0
    assert audio.content_type == "audio/wav"


def test_deepgram_refuses_hindi() -> None:
    with pytest.raises(ValueError, match="no Hindi"):
        DeepgramTTS("key").synthesize("नमस्ते", Language.HI)


def test_local_runtime_needs_no_credentials(settings: AppSettings) -> None:
    adapters = build_adapters(settings)
    assert adapters.tts.provider_for(Language.EN).name == "stub"
    assert adapters.tts.provider_for(Language.HI).name == "stub"
