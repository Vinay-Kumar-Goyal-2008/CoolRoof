"""Text-to-speech (M18+19).

Routing (spec M18+19, fact F10): English → Deepgram Aura-2, Hindi → Amazon Polly,
because Deepgram TTS has no Hindi voice. Without credentials each language falls
back to a silent-WAV stub so the advisory workflow still runs locally.
"""

from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from packages.core.enums import Language
from packages.core.errors import UpstreamError

if TYPE_CHECKING:
    from mypy_boto3_polly import PollyClient

__all__ = [
    "AudioResult",
    "DeepgramTTS",
    "LanguageRoutedTTS",
    "PollyTTS",
    "SilentWavStub",
    "TTSProvider",
]

DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"


@dataclass(frozen=True)
class AudioResult:
    audio: bytes
    content_type: str
    provider: str
    voice: str

    @property
    def extension(self) -> str:
        return {"audio/mpeg": "mp3", "audio/wav": "wav"}.get(self.content_type, "bin")


class TTSProvider(ABC):
    name: str

    @abstractmethod
    def synthesize(self, text: str, lang: Language) -> AudioResult: ...


class SilentWavStub(TTSProvider):
    """Silence whose length scales with the text — keeps the pipeline testable offline."""

    name = "stub"

    def synthesize(self, text: str, lang: Language) -> AudioResult:
        rate = 8000
        seconds = min(max(len(text) / 15.0, 0.5), 60.0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b"\x00\x00" * int(rate * seconds))
        return AudioResult(buf.getvalue(), "audio/wav", self.name, f"silent-{lang.value}")


class DeepgramTTS(TTSProvider):
    """Deepgram Aura-2 (English only)."""

    name = "deepgram"

    def __init__(self, api_key: str, voice: str = "aura-2-thalia-en", timeout_s: float = 20.0):
        self._key = api_key
        self._voice = voice
        self._timeout = timeout_s

    def synthesize(self, text: str, lang: Language) -> AudioResult:
        if lang is not Language.EN:
            raise ValueError("Deepgram TTS has no Hindi voice (F10); route Hindi to Polly")
        try:
            res = httpx.post(
                DEEPGRAM_SPEAK_URL,
                params={"model": self._voice},
                headers={"Authorization": f"Token {self._key}"},
                json={"text": text},
                timeout=self._timeout,
            )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError(f"deepgram tts failed: {exc}") from exc
        return AudioResult(
            res.content, res.headers.get("content-type", "audio/mpeg"), self.name, self._voice
        )


class PollyTTS(TTSProvider):
    """Amazon Polly Hindi voice (neural ``Kajal`` by default; [R] verify in region)."""

    name = "polly"

    def __init__(
        self, voice: str = "Kajal", engine: str = "neural", client: PollyClient | None = None
    ) -> None:
        import boto3

        self._voice = voice
        self._engine = engine
        self._polly: PollyClient = client or boto3.client("polly")

    def synthesize(self, text: str, lang: Language) -> AudioResult:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            res = self._polly.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=self._voice,  # type: ignore[arg-type]
                Engine=self._engine,  # type: ignore[arg-type]
                LanguageCode="hi-IN" if lang is Language.HI else "en-IN",
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamError(f"polly tts failed: {exc}") from exc
        return AudioResult(res["AudioStream"].read(), "audio/mpeg", self.name, self._voice)


class LanguageRoutedTTS(TTSProvider):
    """Picks the provider per language; the M18+19 service handles failures (text only)."""

    name = "routed"

    def __init__(self, english: TTSProvider, hindi: TTSProvider) -> None:
        self._by_lang = {Language.EN: english, Language.HI: hindi}

    def provider_for(self, lang: Language) -> TTSProvider:
        return self._by_lang[lang]

    def synthesize(self, text: str, lang: Language) -> AudioResult:
        return self._by_lang[lang].synthesize(text, lang)
