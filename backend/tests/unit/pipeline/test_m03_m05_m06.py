"""Verify bullets for M3+4 (masking, low confidence), M5 (LST sanity) and M6 (heat analysis)."""

from __future__ import annotations

import numpy as np
from scipy import stats

from packages.pipeline.landcover import WorldCover
from packages.pipeline.m06_heat import rank_stability_leave_one_year_out
from packages.pipeline.runner import PipelineRun


# ------------------------------------------------------------------ M3+4
def test_all_three_scenes_read_with_valid_pixel_pct_logged(mini_run: PipelineRun) -> None:
    stack = mini_run.require(mini_run.stack, "M3+4")
    assert stack.n_scenes == 3
    pcts = {s.scene_id: s.valid_pixel_pct for s in stack.scenes}
    assert all(0 < p <= 100 for p in pcts.values())
    # the cloudy scene loses its cloud, shadow and dilated-cloud pixels
    assert pcts["LC08_MINI_20250418"] < pcts["LC09_MINI_20240415"] - 3


def test_cloud_pixels_are_masked_not_kept_as_cold_values(mini_run: PipelineRun) -> None:
    stack = mini_run.require(mini_run.stack, "M3+4")
    cloudy = stack.st_kelvin[1]
    assert np.nanmin(cloudy) > 295.0  # planted cloud tops were 290 K


def test_scale_and_offset_come_from_metadata(mini_run: PipelineRun) -> None:
    lst = mini_run.require(mini_run.lst, "M5")
    assert 20.0 < np.nanmedian(lst.median_c) < 55.0


def test_ward_under_the_cloud_is_low_confidence(mini_run: PipelineRun) -> None:
    table = mini_run.require(mini_run.heat, "M6").table
    assert bool(table.loc["W11", "low_confidence"])
    assert not bool(table.loc["W01", "low_confidence"])


# ------------------------------------------------------------------ M5
def test_water_is_cooler_than_built_up(mini_run: PipelineRun) -> None:
    lc = mini_run.require(mini_run.landcover, "M1+2")
    med = mini_run.require(mini_run.lst, "M5").median_c
    assert np.nanmean(med[lc == WorldCover.WATER]) < np.nanmean(med[lc == WorldCover.BUILT]) - 5


def test_lst_and_ndvi_are_negatively_correlated(mini_run: PipelineRun) -> None:
    med = mini_run.require(mini_run.lst, "M5").median_c
    ndvi = mini_run.require(mini_run.heat, "M6").ndvi
    ok = np.isfinite(med) & np.isfinite(ndvi)
    assert stats.pearsonr(med[ok], ndvi[ok]).statistic < 0


def test_range_filter_reports_share_removed(mini_run: PipelineRun) -> None:
    assert mini_run.require(mini_run.lst, "M5").removed_out_of_range_pct >= 0.0


# ------------------------------------------------------------------ M6
def test_city_mean_heat_z_is_zero(mini_run: PipelineRun) -> None:
    heat = mini_run.require(mini_run.heat, "M6")
    assert abs(heat.diagnostics["city_mean_heat_z"]) < 1e-9


def test_rural_reference_is_used(mini_run: PipelineRun) -> None:
    ref = mini_run.require(mini_run.heat, "M6").reference
    assert ref.method == "rural_ring"
    assert ref.n_pixels >= 100


def test_dense_built_wards_are_hotter_than_green_wards(mini_run: PipelineRun) -> None:
    t = mini_run.require(mini_run.heat, "M6").table
    assert t.loc["W07", "mean_dlst_c"] > t.loc["W10", "mean_dlst_c"] + 3
    assert t.loc["W01", "persistence"] > t.loc["W04", "persistence"]


def test_hotspots_sit_on_built_or_bare_land(mini_run: PipelineRun) -> None:
    heat = mini_run.require(mini_run.heat, "M6")
    assert len(heat.hotspots) > 0
    assert heat.diagnostics["hotspot_built_or_bare_share"] > 0.7


def test_episodic_ward_is_hot_in_one_scene_only(mini_run: PipelineRun) -> None:
    lst = mini_run.require(mini_run.lst, "M5")
    t = mini_run.require(mini_run.heat, "M6").table
    years = sorted(lst.per_year_median_c)
    assert len(years) == 3
    assert t.loc["W08", "persistence"] < t.loc["W07", "persistence"]


def test_ranks_stable_when_one_year_is_left_out(mini_run: PipelineRun) -> None:
    heat = mini_run.require(mini_run.heat, "M6")
    taus = rank_stability_leave_one_year_out(
        mini_run.require(mini_run.lst, "M5"),
        heat.reference.reference_lst_c,
        mini_run.require(mini_run.grid, "M1+2"),
        mini_run.require(mini_run.wards, "M1+2").wards_utm,
    )
    assert len(taus) == 3
    assert min(taus.values()) > 0.6


def test_spectral_indices_are_plausible(mini_run: PipelineRun) -> None:
    t = mini_run.require(mini_run.heat, "M6").table
    assert t.loc["W10", "ndvi_mean"] > t.loc["W01", "ndvi_mean"]
    assert t.loc["W03", "bsi_mean"] > t.loc["W10", "bsi_mean"]
