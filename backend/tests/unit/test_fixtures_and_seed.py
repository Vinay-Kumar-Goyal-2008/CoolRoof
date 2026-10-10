"""Stage 0 'done when': fixtures load and seed policy records are queryable."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import rasterio

from packages.adapters.docstore import SQLiteDocStore
from packages.core.city import load_city
from packages.services.policy_store import PolicyStore, PolicyType
from scripts.seed import seed_policies

BACKEND = Path(__file__).resolve().parents[2]


def test_mini_city_fixture_loads(mini_city_dir: Path) -> None:
    wards = gpd.read_file(mini_city_dir / "wards.geojson")
    assert len(wards) == 12
    buildings = gpd.read_parquet(mini_city_dir / "buildings.parquet")
    assert 400 <= len(buildings) <= 600
    with rasterio.open(mini_city_dir / "population.tif") as src:
        assert src.crs.to_epsg() == 32643
    items = sorted((mini_city_dir / "landsat").glob("*/item.json"))
    assert len(items) == 3
    item = json.loads(items[0].read_text(encoding="utf-8"))
    assert "scale" in item["assets"]["lwir11"]["raster:bands"][0]


def test_city_configs_load() -> None:
    mini = load_city("mini_city")
    assert mini.synthetic and mini.discom_for().discom == "TEST-DISCOM"
    assert mini.source("wards").resolve() is not None
    pune = load_city("pune")
    assert pune.source("wards").status == "NV"


def test_seed_policies_round_trip(tmp_path: Path) -> None:
    store = PolicyStore(SQLiteDocStore(tmp_path / "p.db"))
    versions = seed_policies(store, BACKEND / "seed")
    assert "subsidy:ALL:ALL:2024-02-29" in versions
    subsidy = store.get(PolicyType.SUBSIDY, on=date(2026, 10, 10))
    assert subsidy is not None
    assert subsidy.doc["residential"]["tiers"][0]["inr_per_kw"] == 30000
    tariff, level = store.resolve(PolicyType.TARIFF, state="TEST", discom="TEST-DISCOM")
    assert tariff is not None and tariff.is_synthetic and level == "state+discom"
    settlement = store.get(PolicyType.NETMETERING, state="TEST", discom="TEST-DISCOM")
    assert settlement is not None and settlement.doc["mode"] == "net_metering"
    checklist, level = store.resolve(PolicyType.CHECKLIST, state="Maharashtra", discom="MSEDCL")
    assert checklist is not None and level == "national"


def test_policy_effective_date_lookup(tmp_path: Path) -> None:
    store = PolicyStore(SQLiteDocStore(tmp_path / "p.db"))
    store.put(PolicyType.SUBSIDY, {"effective_date": "2024-01-01", "v": 1})
    store.put(PolicyType.SUBSIDY, {"effective_date": "2025-01-01", "v": 2})
    old = store.get(PolicyType.SUBSIDY, on=date(2024, 6, 1))
    new = store.get(PolicyType.SUBSIDY, on=date(2025, 6, 1))
    assert old is not None and old.doc["v"] == 1
    assert new is not None and new.doc["v"] == 2
    assert store.get(PolicyType.SUBSIDY, on=date(2023, 6, 1)) is None
