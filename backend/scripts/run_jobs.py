"""Run one scheduled job by hand (the same code EventBridge / APScheduler run).

python -m scripts.run_jobs fire|heatdome|stale [--city mini_city]
"""

from __future__ import annotations

import argparse

from packages.adapters.registry import build_adapters
from packages.core.params import load_params
from packages.core.settings import get_settings
from packages.services.jobs import refresh_fire, refresh_heatdome, stale_flip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=["fire", "heatdome", "stale"])
    parser.add_argument("--city", default=get_settings().city)
    args = parser.parse_args()
    settings = get_settings()
    adapters = build_adapters(settings)
    params = load_params(settings.config_dir / "params.default.yaml")
    if args.job == "fire":
        print(f"{len(refresh_fire(adapters, settings, params, args.city))} fire events")
    elif args.job == "heatdome":
        print(refresh_heatdome(adapters, settings, params, args.city)["risk"])
    else:
        print(f"{stale_flip(adapters, args.city)} wards flipped")


if __name__ == "__main__":
    main()
