"""M1+2 Verify: every demo centroid in exactly one ward; area within 1–2 % of city; valid geometry."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from packages.core.city import load_city
from packages.core.enums import UnitType
from packages.core.errors import IncompleteError, NotFoundError
from packages.pipeline.m01_location import build_ward_layer
from packages.pipeline.runner import PipelineRun


def test_every_ward_centroid_falls_in_exactly_one_ward(mini_run: PipelineRun) -> None:
    layer = mini_run.require(mini_run.wards, "M1+2")
    for ward_id in layer.ward_ids():
        ref = layer.by_id(ward_id)
        resolved = layer.by_point(*ref.centroid)
        assert resolved.ward_id == ward_id


def test_ward_area_matches_city_area_within_2_percent(mini_run: PipelineRun) -> None:
    layer = mini_run.require(mini_run.wards, "M1+2")
    city_area = layer.wards_utm.union_all().area
    assert abs(layer.wards_utm.area.sum() - city_area) / city_area < 0.02
    assert layer.overlap_area_m2() < 1.0
    assert layer.wards_utm.is_valid.all()


def test_location_ref_carries_state_discom_and_buffered_bbox(mini_run: PipelineRun) -> None:
    ref = mini_run.require(mini_run.wards, "M1+2").by_id("W07")
    assert (ref.state, ref.discom) == ("TEST", "TEST-DISCOM")
    assert ref.bbox[0] < ref.centroid[0] < ref.bbox[2]
    assert ref.area_m2 == pytest.approx(1500 * 1500, rel=0.01)


def test_names_resolve_in_english_and_hindi(mini_run: PipelineRun) -> None:
    layer = mini_run.require(mini_run.wards, "M1+2")
    assert layer.by_name("ward 7 textile lanes").ward_id == "W07"
    assert layer.by_name("वार्ड 7").ward_id == "W07"


def test_point_outside_wards_is_404(mini_run: PipelineRun) -> None:
    with pytest.raises(NotFoundError):
        mini_run.require(mini_run.wards, "M1+2").by_point(73.80, 18.48)


def test_overlapping_wards_ask_the_user() -> None:
    city = load_city("mini_city")
    wards = gpd.GeoDataFrame(
        {"ward_id": ["A", "B"], "name": ["A", "B"], "name_hi": ["A", "B"]},
        geometry=[box(73.82, 18.50, 73.84, 18.52), box(73.83, 18.50, 73.85, 18.52)],
        crs="EPSG:4326",
    )
    layer = build_ward_layer(city, wards, "test")
    with pytest.raises(IncompleteError) as exc:
        layer.by_point(73.835, 18.51)
    assert set(exc.value.details["candidates"]) == {"A", "B"}


def test_address_without_geocoder_asks_for_a_click(mini_run: PipelineRun) -> None:
    with pytest.raises(IncompleteError):
        mini_run.require(mini_run.wards, "M1+2").by_address("12 MG Road")


def test_missing_ward_layer_falls_back_to_grid() -> None:
    layer = build_ward_layer(load_city("mini_city"), None, "none")
    assert layer.unit_type is UnitType.GRID
    assert len(layer.wards) > 50
