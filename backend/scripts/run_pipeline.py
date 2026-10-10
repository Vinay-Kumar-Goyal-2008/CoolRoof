"""Run the heat pipeline for a city and persist the results (+ heat-dome forecast).

uv run poe pipeline-mini      # or: python -m scripts.run_pipeline --city mini_city
"""

from __future__ import annotations

import argparse
from datetime import date

from packages.adapters.registry import build_adapters
from packages.core.city import load_city
from packages.core.params import load_params
from packages.core.settings import get_settings
from packages.pipeline.inputs import CityInputs
from packages.pipeline.m43_heatdome import forecast_heatdome, load_nwp_fixture
from packages.pipeline.runner import HeatPipeline, landsat_source_for
from packages.services.policy_store import PolicyStore
from packages.services.repository import Repository
from scripts.seed import seed_policies


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default=get_settings().city)
    parser.add_argument("--date", default=None, help="run date YYYY-MM-DD (default today)")
    args = parser.parse_args()
    settings = get_settings()
    adapters = build_adapters(settings)
    city = load_city(args.city)
    inputs = CityInputs(city)
    pipeline = HeatPipeline(
        city,
        load_params(settings.config_dir / "params.default.yaml"),
        landsat_source_for(settings, inputs),
        run_date=date.fromisoformat(args.date) if args.date else None,
    )
    run = pipeline.run_all()
    forecast = forecast_heatdome(load_nwp_fixture(inputs.nwp_path), run.params).to_dict()
    Repository(adapters.docstore, adapters.blobstore).persist(run, forecast)
    seed_policies(PolicyStore(adapters.docstore), settings.seed_dir)
    top = run.priority.scores[:3]  # type: ignore[union-attr]
    print(
        f"{city.slug}: {len(run.contexts)} wards, {len(run.roof_contexts)} roofs; "
        f"top wards {[s.ward_id for s in top]}; heat-dome risk {forecast['risk']}"
    )


if __name__ == "__main__":
    main()
