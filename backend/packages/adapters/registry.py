"""Builds the adapter set for the current runtime (``RUNTIME=local|aws``).

Application code receives an ``Adapters`` bundle instead of constructing
adapters itself, so tests can swap any piece.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.adapters.blobstore import BlobStore, LocalBlobStore, S3BlobStore
from packages.adapters.docstore import DocStore, DynamoDocStore, SQLiteDocStore
from packages.adapters.notifier import FileNotifier, Notifier, SNSNotifier
from packages.adapters.scheduler import APSchedulerLocal, EventBridgeScheduler, Scheduler
from packages.adapters.secrets import EnvSecrets, Secrets, SecretsManagerSecrets
from packages.adapters.tts import (
    DeepgramTTS,
    LanguageRoutedTTS,
    PollyTTS,
    SilentWavStub,
    TTSProvider,
)
from packages.core.enums import Runtime
from packages.core.settings import AppSettings

__all__ = ["Adapters", "build_adapters"]


@dataclass
class Adapters:
    """Every external dependency, behind its interface."""

    blobstore: BlobStore
    docstore: DocStore
    notifier: Notifier
    scheduler: Scheduler
    secrets: Secrets
    tts: LanguageRoutedTTS


def _require(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"RUNTIME=aws requires {name}")
    return value


def _build_tts(settings: AppSettings, secrets: Secrets) -> LanguageRoutedTTS:
    stub = SilentWavStub()
    deepgram_key = secrets.get("DEEPGRAM_API_KEY")
    english: TTSProvider = DeepgramTTS(deepgram_key) if deepgram_key else stub
    hindi: TTSProvider = (
        PollyTTS() if settings.runtime is Runtime.AWS or settings.aws_region else stub
    )
    return LanguageRoutedTTS(english=english, hindi=hindi)


def build_adapters(settings: AppSettings) -> Adapters:
    """Construct adapters for ``settings.runtime``."""
    if settings.runtime is Runtime.AWS:
        secrets: Secrets = SecretsManagerSecrets(f"{settings.dynamodb_table_prefix}/app")
        arn_prefix = _require(secrets.get("SNS_ARN_PREFIX"), "SNS_ARN_PREFIX secret")
        return Adapters(
            blobstore=S3BlobStore(_require(settings.s3_bucket, "S3_BUCKET")),
            docstore=DynamoDocStore(settings.dynamodb_table_prefix),
            notifier=SNSNotifier(settings.sns_topic_prefix, arn_prefix),
            scheduler=EventBridgeScheduler(),
            secrets=secrets,
            tts=_build_tts(settings, secrets),
        )

    secrets = EnvSecrets(settings)
    return Adapters(
        blobstore=LocalBlobStore(settings.blob_root),
        docstore=SQLiteDocStore(settings.sqlite_path),
        notifier=FileNotifier(settings.outbox_dir),
        scheduler=APSchedulerLocal(),
        secrets=secrets,
        tts=_build_tts(settings, secrets),
    )
