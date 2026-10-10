"""DocStore contract tests (run against the SQLite implementation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.adapters.docstore import Index, SQLiteDocStore, Table


@pytest.fixture
def store(tmp_path: Path) -> SQLiteDocStore:
    return SQLiteDocStore(tmp_path / "t.db")


def test_put_get_round_trip_keeps_unicode(store: SQLiteDocStore) -> None:
    store.put(Table.POLICY, "policy#subsidy#ALL#ALL", "2024-02-29", {"name": "पीएम सूर्य घर"})
    assert store.get(Table.POLICY, "policy#subsidy#ALL#ALL", "2024-02-29") == {
        "name": "पीएम सूर्य घर"
    }


def test_query_orders_by_sort_key_and_latest(store: SQLiteDocStore) -> None:
    for sk in ["ctx#2026-01-01", "ctx#2026-03-01", "reco#x", "ctx#2026-02-01"]:
        store.put(Table.WARD_CONTEXT, "mini#W01", sk, {"sk": sk})
    rows = store.query(Table.WARD_CONTEXT, "mini#W01", sk_prefix="ctx#")
    assert [r["sk"] for r in rows] == ["ctx#2026-01-01", "ctx#2026-02-01", "ctx#2026-03-01"]
    latest = store.latest(Table.WARD_CONTEXT, "mini#W01", sk_prefix="ctx#")
    assert latest == {"sk": "ctx#2026-03-01"}


def test_if_absent_does_not_overwrite(store: SQLiteDocStore) -> None:
    assert store.put(Table.ALERTS, "fire#mini", "k1", {"v": 1}, if_absent=True)
    assert not store.put(Table.ALERTS, "fire#mini", "k1", {"v": 2}, if_absent=True)
    assert store.get(Table.ALERTS, "fire#mini", "k1") == {"v": 1}


def test_ttl_expired_items_are_invisible(store: SQLiteDocStore) -> None:
    store.put(Table.SESSION, "session#a", "-", {"x": 1}, ttl_s=-1)
    assert store.get(Table.SESSION, "session#a") is None
    # and an expired item does not block a new conditional write
    assert store.put(Table.SESSION, "session#a", "-", {"x": 2}, if_absent=True)


def test_secondary_index_ordering(store: SQLiteDocStore) -> None:
    for ward, rank in [("W1", "0003"), ("W2", "0001"), ("W3", "0002")]:
        store.put(
            Table.WARD_CONTEXT,
            f"mini#{ward}",
            "ctx#v1",
            {"w": ward},
            index=Index("city#mini", rank),
        )
    assert [r["w"] for r in store.query_index(Table.WARD_CONTEXT, "city#mini")] == [
        "W2",
        "W3",
        "W1",
    ]


def test_update_paths_is_path_limited_and_conditional(store: SQLiteDocStore) -> None:
    store.put(Table.WARD_CONTEXT, "mini#W1", "ctx#v1", {"heat": {"mean_dlst_c": 3.1}})
    doc = store.update_paths(
        Table.WARD_CONTEXT, "mini#W1", "ctx#v1", {"hazards.fire_events_30d": {"value": 2}}
    )
    assert doc["heat"] == {"mean_dlst_c": 3.1}
    assert doc["hazards"]["fire_events_30d"] == {"value": 2}
    with pytest.raises(KeyError):
        store.update_paths(Table.WARD_CONTEXT, "mini#W9", "ctx#v1", {"a": 1})
