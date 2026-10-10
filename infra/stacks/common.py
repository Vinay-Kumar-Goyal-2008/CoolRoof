"""Shared pieces: deploy-time context and the backend Lambda container (the API and the scheduled jobs share one image)."""

from __future__ import annotations

import re
from pathlib import Path

from aws_cdk import Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

BACKEND = Path(__file__).resolve().parents[2] / "backend"
IMAGE_EXCLUDE = [".venv", "data", "__pycache__", "**/__pycache__", ".*_cache", ".hypothesis",
                 "tests/unit", "tests/e2e", "tests/property", "tests/golden", "assets/fonts/*.ttc"]


def ctx(scope: Construct, key: str, default: str = "") -> str:
    """`cdk deploy -c key=value` (or cdk.context.json); the default when unset or empty."""
    value = scope.node.try_get_context(key)
    return str(value) if value not in (None, "") else default


def fire_poll_minutes() -> int:
    """P-FIRE-POLL from the backend params file, so the EventBridge rate follows the code."""
    text = (BACKEND / "config" / "params.default.yaml").read_text(encoding="utf-8")
    m = re.search(r"P-FIRE-POLL:\s*\n\s*value:\s*(\d+)", text)
    return int(m.group(1)) if m else 30


def data_source_env(mode: str) -> dict[str, str]:
    """`fixture` keeps the synthetic city offline; `live` switches every source to its real service."""
    if mode == "live":
        return {"LANDSAT_SOURCE": "planetary_computer", "NWP_SOURCE": "open_meteo",
                "SOLAR_SOURCE": "live", "FIRMS_SOURCE": "live"}
    return {}


def backend_function(scope: Construct, construct_id: str, *, handler: str, environment: dict[str, str],
                     timeout: Duration, memory_size: int = 2048) -> _lambda.DockerImageFunction:
    return _lambda.DockerImageFunction(
        scope, construct_id,
        code=_lambda.DockerImageCode.from_image_asset(
            str(BACKEND), file="Dockerfile.lambda", exclude=IMAGE_EXCLUDE, cmd=[handler]),
        memory_size=memory_size, timeout=timeout, environment=environment,
    )


def bedrock_policy() -> iam.PolicyStatement:
    return iam.PolicyStatement(
        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        resources=["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:*:*:inference-profile/*"])
