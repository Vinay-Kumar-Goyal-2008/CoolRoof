"""Notifier: publishes alert messages. Local = JSON files in the outbox, AWS = SNS."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packages.core.ids import new_uuid
from packages.core.timeutil import utc_now

if TYPE_CHECKING:
    from mypy_boto3_sns import SNSClient

__all__ = ["FileNotifier", "Notifier", "SNSNotifier"]


class Notifier(ABC):
    """Interface: publish one message to a topic with filterable attributes."""

    @abstractmethod
    def publish(
        self,
        topic: str,
        subject: str,
        message: Mapping[str, Any],
        attributes: Mapping[str, str],
    ) -> str:
        """Publish and return the message id."""


class FileNotifier(Notifier):
    """Writes each message to ``<outbox>/<topic>/<timestamp>_<id>.json``."""

    def __init__(self, outbox: Path) -> None:
        self._outbox = outbox

    def publish(
        self,
        topic: str,
        subject: str,
        message: Mapping[str, Any],
        attributes: Mapping[str, str],
    ) -> str:
        message_id = new_uuid()
        folder = self._outbox / topic
        folder.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%dT%H%M%S%f")
        payload = {
            "message_id": message_id,
            "topic": topic,
            "subject": subject,
            "attributes": dict(attributes),
            "message": dict(message),
            "published_at": utc_now().isoformat(),
        }
        (folder / f"{stamp}_{message_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return message_id

    def read_outbox(self, topic: str | None = None) -> list[dict[str, Any]]:
        """All messages written so far (tests and the demo use this)."""
        root = self._outbox / topic if topic else self._outbox
        if not root.exists():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.rglob("*.json"))]


class SNSNotifier(Notifier):
    """Amazon SNS: topic name ``<prefix>-<topic>`` (one per city and audience)."""

    def __init__(self, topic_prefix: str, account_arn_prefix: str, client: SNSClient | None = None):
        import boto3

        self._prefix = topic_prefix
        self._arn_prefix = account_arn_prefix  # e.g. "arn:aws:sns:ap-south-1:123456789012"
        self._sns: SNSClient = client or boto3.client("sns")

    def publish(
        self,
        topic: str,
        subject: str,
        message: Mapping[str, Any],
        attributes: Mapping[str, str],
    ) -> str:
        res = self._sns.publish(
            TopicArn=f"{self._arn_prefix}:{self._prefix}-{topic}",
            Subject=subject[:100],
            Message=json.dumps(message, ensure_ascii=False),
            MessageAttributes={
                k: {"DataType": "String", "StringValue": v} for k, v in attributes.items()
            },
        )
        return res["MessageId"]
