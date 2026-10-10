"""One pipeline run over the mini city, shared by all pipeline tests (session scope)."""

from __future__ import annotations

from datetime import date

import pytest

from packages.adapters.landsat_source import FixtureLandsatSource
from packages.core.city import load_city
from packages.core.params import load_params
from packages.pipeline.inputs import CityInputs
from packages.pipeline.runner import HeatPipeline, PipelineRun

RUN_DATE = date(2026, 10, 10)


@pytest.fixture(scope="session")
def mini_run() -> PipelineRun:
    city = load_city("mini_city")
    inputs = CityInputs(city)
    assert inputs.landsat_items_dir is not None
    pipeline = HeatPipeline(
        city,
        load_params(),
        FixtureLandsatSource(inputs.landsat_items_dir),
        run_date=RUN_DATE,
        run_id="test_run",
    )
    return pipeline.run_all()
