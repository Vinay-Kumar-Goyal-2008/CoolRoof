"""Typed application settings loaded from environment variables / ``backend/.env``.

All secrets are optional: when a key is missing, the matching adapter falls back
to its local stub (rule 6, local-first).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from packages.core.enums import Runtime

__all__ = ["BACKEND_ROOT", "AppSettings", "get_settings"]

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseSettings):
    """Process configuration. Field names map to upper-case environment variables."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    runtime: Runtime = Runtime.LOCAL
    city: str = "pune"
    log_level: str = "INFO"

    # Local storage
    data_dir: Path = BACKEND_ROOT / "data"
    config_dir: Path = BACKEND_ROOT / "config"
    rules_dir: Path = BACKEND_ROOT / "rules"
    seed_dir: Path = BACKEND_ROOT / "seed"
    rules_version: str = "v1"

    # Source selection for local runs ("fixture" = offline mini-city data)
    landsat_source: str = Field(default="fixture", pattern="^(fixture|planetary_computer)$")
    nwp_source: str = Field(default="fixture", pattern="^(fixture|open_meteo)$")
    solar_source: str = Field(default="fixture", pattern="^(fixture|live)$")
    firms_source: str = Field(default="fixture", pattern="^(fixture|live)$")

    # Optional credentials (stubs are used when absent)
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    bedrock_model_id: str | None = None
    deepgram_api_key: SecretStr | None = None
    firms_map_key: SecretStr | None = None
    aws_region: str | None = None

    # AWS resource names (used when RUNTIME=aws)
    s3_bucket: str | None = None
    dynamodb_table_prefix: str = "coolroof"
    sns_topic_prefix: str = "coolroof"

    # API
    frontend_origin: str = "http://localhost:3000"
    planner_api_key: SecretStr | None = None
    admin_api_key: SecretStr | None = None
    session_ttl_hours: int = 24
    enable_jobs: bool = False  # schedule fire poll / daily forecast / staleness locally
    advisory_two_person: bool = False
    tts_daily_cap: int = 200

    # Cognito (optional): when set, Bearer ID/access tokens are verified and mapped to roles
    cognito_issuer: str | None = None  # https://cognito-idp.<region>.amazonaws.com/<pool-id>
    cognito_client_id: str | None = None
    agent_timeout_s: float = 25.0
    agent_max_turns: int = 40

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "coolroof.db"

    @property
    def blob_root(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Cached settings singleton (tests build their own ``AppSettings`` instead)."""
    return AppSettings()
