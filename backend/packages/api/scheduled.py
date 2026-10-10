"""Lambda entry point for the EventBridge schedules (``packages.api.scheduled.handler``).

The CDK jobs stack sends ``{"job": "fire" | "heatdome" | "stale"}``; each job is idempotent and
runs the same code as ``scripts/run_jobs.py`` and the local APScheduler.
"""

from __future__ import annotations

from typing import Any

from packages.adapters.registry import Adapters, build_adapters
from packages.adapters.secrets import apply_secret_settings
from packages.api.routers.admin import load_overrides
from packages.core.logging import configure_logging, get_logger
from packages.core.params import ParamRegistry, load_params
from packages.core.settings import AppSettings, get_settings
from packages.services.jobs import refresh_fire, refresh_heatdome, stale_flip

__all__ = ["JOBS", "handler", "run_job"]

JOBS = ("fire", "heatdome", "stale")
_log = get_logger(__name__)


def run_job(
    event: dict[str, Any],
    settings: AppSettings,
    adapters: Adapters,
    params: ParamRegistry,
) -> dict[str, Any]:
    job = str(event.get("job", ""))
    city = str(event.get("city") or settings.city)
    if job == "fire":
        return {
            "job": job,
            "city": city,
            "events": len(refresh_fire(adapters, settings, params, city)),
        }
    if job == "heatdome":
        return {
            "job": job,
            "city": city,
            "risk": refresh_heatdome(adapters, settings, params, city)["risk"],
        }
    if job == "stale":
        return {"job": job, "city": city, "wards_flipped": stale_flip(adapters, city)}
    raise ValueError(f"unknown job {job!r}; expected one of {', '.join(JOBS)}")


def handler(event: dict[str, Any], _context: object = None) -> dict[str, Any]:
    settings = get_settings()
    configure_logging(settings.log_level)
    adapters = build_adapters(settings)
    settings = apply_secret_settings(settings, adapters.secrets)
    params = load_overrides(
        load_params(settings.config_dir / "params.default.yaml"), adapters.docstore
    )
    result = run_job(event, settings, adapters, params)
    _log.info("scheduled_job_done", **result)
    return result
