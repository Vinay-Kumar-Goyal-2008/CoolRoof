"""DocStore: JSON documents keyed by partition key + sort key.

Local = SQLite (one physical table, same PK/SK scheme), AWS = DynamoDB (one
table per logical table, §M40). Both support one secondary index (``gsi1``)
used for "wards of a city by priority rank" and "advisories by status".

Documents are stored as JSON text so floats survive DynamoDB unchanged.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table as DynamoTable

__all__ = ["DocStore", "DynamoDocStore", "Index", "SQLiteDocStore", "Table", "set_path"]

NO_SORT_KEY = "-"


class Table(StrEnum):
    """Logical tables (§M40)."""

    WARD_CONTEXT = "ward_context"
    ROOF_CONTEXT = "roof_context"
    POLICY = "policy"
    CONFIG = "config"
    SESSION = "session"
    CACHE = "cache"
    ALERTS = "alerts"
    ADVISORIES = "advisories"
    SUBSCRIPTIONS = "subscriptions"
    FORECASTS = "forecasts"
    ENVIRONMENT = "environment"
    RUNS = "runs"


@dataclass(frozen=True)
class Index:
    """Secondary-index key for a document (``gsi1pk`` / ``gsi1sk``)."""

    pk: str
    sk: str


def set_path(doc: dict[str, Any], dotted: str, value: Any) -> None:
    """Set ``doc["a"]["b"] = value`` for ``dotted = "a.b"``, creating dicts as needed."""
    parts = dotted.split(".")
    node = doc
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


class DocStore(ABC):
    """Interface for document storage."""

    @abstractmethod
    def put(
        self,
        table: Table,
        pk: str,
        sk: str,
        doc: Mapping[str, Any],
        *,
        index: Index | None = None,
        ttl_s: int | None = None,
        if_absent: bool = False,
    ) -> bool:
        """Write a document. With ``if_absent`` returns False instead of overwriting."""

    @abstractmethod
    def get(self, table: Table, pk: str, sk: str = NO_SORT_KEY) -> dict[str, Any] | None: ...

    @abstractmethod
    def query(
        self,
        table: Table,
        pk: str,
        *,
        sk_prefix: str | None = None,
        sk_gte: str | None = None,
        sk_lte: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Documents in one partition, ordered by sort key."""

    @abstractmethod
    def query_index(
        self,
        table: Table,
        index_pk: str,
        *,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Documents with the given ``gsi1pk``, ordered by ``gsi1sk``."""

    @abstractmethod
    def delete(self, table: Table, pk: str, sk: str = NO_SORT_KEY) -> None: ...

    @abstractmethod
    def update_paths(
        self, table: Table, pk: str, sk: str, updates: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Path-limited update of an existing document (e.g. ``hazards.fire_events_30d``).

        Raises ``KeyError`` when the document does not exist (conditional update).
        """

    def latest(
        self, table: Table, pk: str, *, sk_prefix: str | None = None
    ) -> dict[str, Any] | None:
        """The document with the greatest sort key in a partition."""
        rows = self.query(table, pk, sk_prefix=sk_prefix, descending=True, limit=1)
        return rows[0] if rows else None


# ============================================================================ SQLite
_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    tbl        TEXT NOT NULL,
    pk         TEXT NOT NULL,
    sk         TEXT NOT NULL,
    doc        TEXT NOT NULL,
    gsi1pk     TEXT,
    gsi1sk     TEXT,
    expires_at REAL,
    PRIMARY KEY (tbl, pk, sk)
);
CREATE INDEX IF NOT EXISTS items_gsi1 ON items (tbl, gsi1pk, gsi1sk);
"""


class SQLiteDocStore(DocStore):
    """SQLite implementation (thread-safe via a lock; WAL mode)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    @staticmethod
    def _alive_clause() -> tuple[str, float]:
        return "(expires_at IS NULL OR expires_at > ?)", time.time()

    def put(
        self,
        table: Table,
        pk: str,
        sk: str,
        doc: Mapping[str, Any],
        *,
        index: Index | None = None,
        ttl_s: int | None = None,
        if_absent: bool = False,
    ) -> bool:
        expires = time.time() + ttl_s if ttl_s else None
        verb = "INSERT OR IGNORE" if if_absent else "INSERT OR REPLACE"
        with self._cursor() as cur:
            if if_absent:  # an expired row does not block a new write
                cur.execute(
                    "DELETE FROM items WHERE tbl=? AND pk=? AND sk=? AND expires_at <= ?",
                    (table.value, pk, sk, time.time()),
                )
            cur.execute(
                f"{verb} INTO items (tbl, pk, sk, doc, gsi1pk, gsi1sk, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    table.value,
                    pk,
                    sk,
                    json.dumps(doc, ensure_ascii=False),
                    index.pk if index else None,
                    index.sk if index else None,
                    expires,
                ),
            )
            return cur.rowcount > 0

    def get(self, table: Table, pk: str, sk: str = NO_SORT_KEY) -> dict[str, Any] | None:
        alive, now = self._alive_clause()
        with self._cursor() as cur:
            row = cur.execute(
                f"SELECT doc FROM items WHERE tbl=? AND pk=? AND sk=? AND {alive}",
                (table.value, pk, sk, now),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def query(
        self,
        table: Table,
        pk: str,
        *,
        sk_prefix: str | None = None,
        sk_gte: str | None = None,
        sk_lte: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        alive, now = self._alive_clause()
        sql = f"SELECT doc FROM items WHERE tbl=? AND pk=? AND {alive}"
        args: list[Any] = [table.value, pk, now]
        if sk_prefix is not None:
            sql += " AND substr(sk, 1, ?) = ?"
            args += [len(sk_prefix), sk_prefix]
        if sk_gte is not None:
            sql += " AND sk >= ?"
            args.append(sk_gte)
        if sk_lte is not None:
            sql += " AND sk <= ?"
            args.append(sk_lte)
        sql += f" ORDER BY sk {'DESC' if descending else 'ASC'}"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._cursor() as cur:
            rows = cur.execute(sql, args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def query_index(
        self,
        table: Table,
        index_pk: str,
        *,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        alive, now = self._alive_clause()
        sql = (
            f"SELECT doc FROM items WHERE tbl=? AND gsi1pk=? AND {alive} "
            f"ORDER BY gsi1sk {'DESC' if descending else 'ASC'}"
        )
        args: list[Any] = [table.value, index_pk, now]
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self._cursor() as cur:
            rows = cur.execute(sql, args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete(self, table: Table, pk: str, sk: str = NO_SORT_KEY) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM items WHERE tbl=? AND pk=? AND sk=?", (table.value, pk, sk))

    def update_paths(
        self, table: Table, pk: str, sk: str, updates: Mapping[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT doc FROM items WHERE tbl=? AND pk=? AND sk=?", (table.value, pk, sk)
            ).fetchone()
            if row is None:
                raise KeyError(f"{table.value}:{pk}/{sk} does not exist")
            doc: dict[str, Any] = json.loads(row[0])
            for path, value in updates.items():
                set_path(doc, path, value)
            self._conn.execute(
                "UPDATE items SET doc=? WHERE tbl=? AND pk=? AND sk=?",
                (json.dumps(doc, ensure_ascii=False), table.value, pk, sk),
            )
        return doc


# ============================================================================ DynamoDB
class DynamoDocStore(DocStore):
    """DynamoDB implementation: table ``<prefix>-<logical>``, GSI named ``gsi1``.

    Attributes: ``pk``, ``sk``, ``doc`` (JSON string), ``gsi1pk``, ``gsi1sk``,
    ``expires_at`` (TTL attribute, epoch seconds).
    """

    def __init__(self, table_prefix: str, resource: Any | None = None) -> None:
        import boto3

        self._prefix = table_prefix
        self._db = resource or boto3.resource("dynamodb")

    def _table(self, table: Table) -> DynamoTable:
        return self._db.Table(f"{self._prefix}-{table.value}")

    def put(
        self,
        table: Table,
        pk: str,
        sk: str,
        doc: Mapping[str, Any],
        *,
        index: Index | None = None,
        ttl_s: int | None = None,
        if_absent: bool = False,
    ) -> bool:
        from botocore.exceptions import ClientError

        item: dict[str, Any] = {"pk": pk, "sk": sk, "doc": json.dumps(doc, ensure_ascii=False)}
        if index:
            item |= {"gsi1pk": index.pk, "gsi1sk": index.sk}
        if ttl_s:
            item["expires_at"] = int(time.time() + ttl_s)
        kwargs: dict[str, Any] = {"Item": item}
        if if_absent:
            kwargs["ConditionExpression"] = "attribute_not_exists(pk)"
        try:
            self._table(table).put_item(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def get(self, table: Table, pk: str, sk: str = NO_SORT_KEY) -> dict[str, Any] | None:
        res = self._table(table).get_item(Key={"pk": pk, "sk": sk})
        item = res.get("Item")
        if not item or _expired(item):
            return None
        return _load(item)

    def query(
        self,
        table: Table,
        pk: str,
        *,
        sk_prefix: str | None = None,
        sk_gte: str | None = None,
        sk_lte: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import ConditionBase, Key

        cond: ConditionBase = Key("pk").eq(pk)
        if sk_prefix is not None:
            cond &= Key("sk").begins_with(sk_prefix)
        elif sk_gte is not None and sk_lte is not None:
            cond &= Key("sk").between(sk_gte, sk_lte)
        elif sk_gte is not None:
            cond &= Key("sk").gte(sk_gte)
        elif sk_lte is not None:
            cond &= Key("sk").lte(sk_lte)
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": cond,
            "ScanIndexForward": not descending,
        }
        if limit:
            kwargs["Limit"] = limit
        items = self._table(table).query(**kwargs).get("Items", [])
        return [_load(i) for i in items if not _expired(i)]

    def query_index(
        self,
        table: Table,
        index_pk: str,
        *,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        kwargs: dict[str, Any] = {
            "IndexName": "gsi1",
            "KeyConditionExpression": Key("gsi1pk").eq(index_pk),
            "ScanIndexForward": not descending,
        }
        if limit:
            kwargs["Limit"] = limit
        items = self._table(table).query(**kwargs).get("Items", [])
        return [_load(i) for i in items if not _expired(i)]

    def delete(self, table: Table, pk: str, sk: str = NO_SORT_KEY) -> None:
        self._table(table).delete_item(Key={"pk": pk, "sk": sk})

    def update_paths(
        self, table: Table, pk: str, sk: str, updates: Mapping[str, Any]
    ) -> dict[str, Any]:
        # Read-modify-write guarded by an optimistic check on the previous JSON.
        from botocore.exceptions import ClientError

        tbl = self._table(table)
        item = tbl.get_item(Key={"pk": pk, "sk": sk}).get("Item")
        if not item:
            raise KeyError(f"{table.value}:{pk}/{sk} does not exist")
        previous = str(item["doc"])
        doc: dict[str, Any] = json.loads(previous)
        for path, value in updates.items():
            set_path(doc, path, value)
        try:
            tbl.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET #d = :new",
                ConditionExpression="#d = :old",
                ExpressionAttributeNames={"#d": "doc"},
                ExpressionAttributeValues={
                    ":new": json.dumps(doc, ensure_ascii=False),
                    ":old": previous,
                },
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return self.update_paths(table, pk, sk, updates)  # concurrent write: retry
            raise
        return doc


def _load(item: Mapping[str, Any]) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(str(item["doc"]))
    return doc


def _expired(item: Mapping[str, Any]) -> bool:
    expires = item.get("expires_at")
    return expires is not None and float(expires) <= time.time()
