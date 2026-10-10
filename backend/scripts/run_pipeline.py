"""Run the heat pipeline for a city, persist the results and raise the staff alerts.

uv run poe pipeline-mini      # or: python -m scripts.run_pipeline --city mini_city
"""

from __future__ import annotations

import argparse
from datetime import date

from packages.adapters.registry import build_adapters
from packages.core.params import load_params
from packages.core.settings import get_settings
from packages.services.analysis import run_and_persist
from packages.services.policy_store import PolicyStore
from scripts.seed import seed_policies


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default=get_settings().city)
    parser.add_argument("--date", default=None, help="run date YYYY-MM-DD (default today)")
    args = parser.parse_args()
    settings = get_settings()
    adapters = build_adapters(settings)
    seed_policies(PolicyStore(adapters.docstore), settings.seed_dir)
    result = run_and_persist(
        settings,
        adapters,
        load_params(settings.config_dir / "params.default.yaml"),
        args.city,
        run_date=date.fromisoformat(args.date) if args.date else None,
    )
    s = result["summary"]
    print(
        f"{args.city}: {s['wards']} wards, {s['roofs']} roofs; top wards {s['top_wards']}; "
        f"heat-dome risk {s['heatdome_risk']}; steps {result['steps']}"
    )


if __name__ == "__main__":
    main()
