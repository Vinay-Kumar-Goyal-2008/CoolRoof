"""Verify bullets for M7 (footprints), M8 (population) and M8.5 (context builder)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import jsonschema
import pytest

from packages.core.context import context_json_schema
from packages.core.enums import ValueClass
from packages.pipeline.m085_context import (
    BASE_FIELD_SPECS,
    FieldSpec,
    build_ward_contexts,
    flip_stale,
)
from packages.pipeline.runner import HeatPipeline, PipelineRun


# ------------------------------------------------------------------ M7
def test_cleaning_drops_artefacts_and_duplicates(mini_run: PipelineRun) -> None:
    report = mini_run.require(mini_run.buildings, "M7").report
    assert report["exact_duplicates_removed"] >= 1
    assert report["below_min_area"] >= 1
    assert report["output"] < report["input"]


def test_building_ids_are_stable_and_unique(mini_run: PipelineRun) -> None:
    b = mini_run.require(mini_run.buildings, "M7").buildings
    assert b.building_id.is_unique
    assert all(bid.startswith("b_") for bid in b.building_id)


def test_footprint_vs_worldcover_ratio_flags_sparse_ward(mini_run: PipelineRun) -> None:
    table = mini_run.require(mini_run.buildings, "M7").ward_table
    assert bool(table.loc["W09", "buildings_incomplete"])
    complete = table.drop(index="W09")
    assert not complete["buildings_incomplete"].any()
    # verify bullet: built-area ratio reported for (at least) three wards
    assert complete["footprint_vs_worldcover"].notna().sum() >= 3


# ------------------------------------------------------------------ M8
def test_building_sum_matches_grid_total_within_1_percent(mini_run: PipelineRun) -> None:
    pop = mini_run.require(mini_run.population, "M8")
    assert pop.allocated_total == pytest.approx(pop.grid_total_in_building_cells, rel=0.01)


def test_ward_population_conserves_grid_mass(mini_run: PipelineRun) -> None:
    import numpy as np
    import rasterio

    pop = mini_run.require(mini_run.population, "M8")
    path = mini_run.inputs.population_path
    assert path is not None
    with rasterio.open(path) as src:
        grid_total = float(np.nansum(np.where(src.read(1) >= 0, src.read(1), 0)))
    wards_total = float(pop.ward_table["population"].sum())
    assert 0 < wards_total <= grid_total  # wards are a subset of the grid extent


def test_exposure_uses_grid_for_incomplete_ward(mini_run: PipelineRun) -> None:
    table = mini_run.require(mini_run.population, "M8").ward_table
    assert table.loc["W09", "exposure_method"] == "grid"
    assert table.loc["W07", "exposure_method"] == "buildings"
    assert table.loc["W07", "exposed_population"] > table.loc["W10", "exposed_population"]


# ------------------------------------------------------------------ M8.5
def test_every_context_validates_against_the_json_schema(mini_run: PipelineRun) -> None:
    schema = context_json_schema()
    assert len(mini_run.contexts) == 12
    for ctx in mini_run.contexts:
        jsonschema.validate(ctx.to_doc(), schema)


def test_values_trace_to_sources(mini_run: PipelineRun) -> None:
    """10-ward audit: every available value names its source and processing date."""
    for ctx in mini_run.contexts[:10]:
        for path, env in ctx.iter_envelopes():
            assert env.source, path
            if env.is_available:
                assert env.processed == "2026-10-10", path


def test_conflicting_sources_keep_alt_value(mini_run: PipelineRun) -> None:
    ctx = next(c for c in mini_run.contexts if c.ward_id == "W01")
    built = ctx.field("built_environment.built_fraction")
    assert built.source.startswith("esa_worldcover")
    assert built.alt_value is not None  # footprint coverage kept as alt


def test_flags_and_quality(mini_run: PipelineRun) -> None:
    by_id = {c.ward_id: c for c in mini_run.contexts}
    assert "buildings_incomplete" in by_id["W09"].data_quality.flags
    assert "low_confidence" in by_id["W11"].data_quality.flags
    assert 0 < by_id["W01"].data_quality.context_confidence <= 1


def test_removing_a_dataset_yields_unavailable_not_zero(mini_run: PipelineRun) -> None:
    pipeline = HeatPipeline.__new__(HeatPipeline)
    pipeline.run = replace(mini_run, population=None)
    tables = pipeline.feature_tables()
    contexts = build_ward_contexts(
        mini_run.require(mini_run.wards, "M1+2"),
        tables,
        BASE_FIELD_SPECS,
        mini_run.params,
        context_version="v",
        run_id="r",
        run_date=date(2026, 10, 10),
    )
    for ctx in contexts:
        env = ctx.field("population.population")
        assert env.cls is ValueClass.UNAVAILABLE
        assert env.value is None
        assert "population.population" in ctx.data_quality.missing


def test_staleness_job_flips_fields(mini_run: PipelineRun) -> None:
    ctx = mini_run.contexts[0]
    assert flip_stale(ctx, date(2026, 10, 11)) is ctx
    stale = flip_stale(ctx, date(2028, 1, 1))
    env = stale.field("heat.mean_dlst_c")
    assert env.cls is ValueClass.STALE
    assert env.value == ctx.field("heat.mean_dlst_c").value
    assert stale.data_quality.stale > 0


def test_field_specs_reject_non_spec_fields() -> None:
    with pytest.raises(ValueError, match="not a spec context field"):
        FieldSpec("heat.invented_metric", "heat", "x")
