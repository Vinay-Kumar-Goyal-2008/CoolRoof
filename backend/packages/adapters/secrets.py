"""Secrets: local = settings / ``.env``, AWS = Secrets Manager (one JSON secret)."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from functools import cached_property
from typing import TYPE_CHECKING

from pydantic import SecretStr

from packages.core.enums import Runtime
from packages.core.settings import AppSettings

if TYPE_CHECKING:
    from mypy_boto3_secretsmanager import SecretsManagerClient

__all__ = ["EnvSecrets", "Secrets", "SecretsManagerSecrets", "apply_secret_settings"]


class Secrets(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None:
        """Secret value by upper-case name (e.g. ``DEEPGRAM_API_KEY``), or None."""


class EnvSecrets(Secrets):
    """Reads typed settings first, then raw environment variables."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def get(self, name: str) -> str | None:
        value = getattr(self._settings, name.lower(), None)
        if value is not None and hasattr(value, "get_secret_value"):
            return str(value.get_secret_value()) or None
        if isinstance(value, str) and value:
            return value
        return os.environ.get(name) or None


class SecretsManagerSecrets(Secrets):
    """One Secrets Manager secret holding a JSON object of name → value."""

    def __init__(self, secret_id: str, client: SecretsManagerClient | None = None) -> None:
        import boto3

        self._secret_id = secret_id
        self._client: SecretsManagerClient = client or boto3.client("secretsmanager")

    @cached_property
    def _values(self) -> dict[str, str]:
        raw = self._client.get_secret_value(SecretId=self._secret_id)["SecretString"]
        data: dict[str, str] = json.loads(raw)
        return data

    def get(self, name: str) -> str | None:
        return self._values.get(name) or None


_SECRET_FIELDS = (
    ("planner_api_key", "PLANNER_API_KEY"),
    ("admin_api_key", "ADMIN_API_KEY"),
    ("firms_map_key", "FIRMS_MAP_KEY"),
)


def apply_secret_settings(settings: AppSettings, secrets: Secrets) -> AppSettings:
    """On AWS, API keys live in Secrets Manager (not Lambda environment variables). Explicit settings win."""
    if settings.runtime is not Runtime.AWS:
        return settings
    updates: dict[str, SecretStr] = {}
    for field, name in _SECRET_FIELDS:
        value = secrets.get(name)
        if getattr(settings, field) is None and value:
            updates[field] = SecretStr(value)
    return settings.model_copy(update=updates) if updates else settings
