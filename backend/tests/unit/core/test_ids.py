from __future__ import annotations

from packages.core.ids import building_id, fire_dedupe_key, input_hash, new_session_id


def test_building_id_is_stable_and_dataset_scoped() -> None:
    wkb = b"\x01\x03geometry"
    assert building_id("google_ob_v3", wkb) == building_id("google_ob_v3", wkb)
    assert building_id("google_ob_v3", wkb) != building_id("overture", wkb)


def test_input_hash_ignores_key_order() -> None:
    assert input_hash({"a": 1, "b": [1, 2]}) == input_hash({"b": [1, 2], "a": 1})


def test_fire_dedupe_key_rounds_to_four_decimals() -> None:
    a = fire_dedupe_key(18.52001, 73.85671, "2026-04-02", "0812", "VIIRS")
    b = fire_dedupe_key(18.52004, 73.85674, "2026-04-02", "0812", "VIIRS")
    c = fire_dedupe_key(18.52010, 73.85671, "2026-04-02", "0812", "VIIRS")
    assert a == b
    assert a != c


def test_session_id_is_128_bit_random() -> None:
    sid = new_session_id()
    assert len(sid) == 32
    assert sid != new_session_id()
