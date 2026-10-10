"""One entry point that runs the heat pipeline for a city and persists everything it produces.

Shared by the CLI (``scripts/run_pipeline``), ``POST /analysis/heat`` and the AWS pipeline task.
Run state is kept in the DocStore (``runs`` table) so a second trigger returns 409.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from packages.adapters.docstore import Table
from packages.adapters.registry import Adapters
from packages.core.city import load_city
from packages.core.errors import ConflictError
from packages.core.ids import new_uuid
from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.core.settings import AppSettings
from packages.core.timeutil import utc_now
from packages.pipeline.inputs import CityInputs
from packages.pipeline.m43_heatdome import forecast_heatdome
from packages.pipeline.runner import HeatPipeline, landsat_source_for
from packages.services.alert_producers import (
    degradation_transitions,
    produce_fire_alerts,
    produce_habitat_alerts,
    produce_heatdome_alert,
    produce_transition_alerts,
)
from packages.services.jobs import firms_source_for, nwp_source_for
from packages.services.m37_alerts import AlertHub
from packages.services.policy_store import PolicyStore, PolicyType
from packages.services.repository import Repository

__all__ = ["claim_run", "get_run", "run_and_persist"]

_log = get_logger("analysis")
STALE_RUN_MINUTES = 60


def get_run(adapters: Adapters, execution_id: str) -> dict[str, Any] | None:
    return adapters.docstore.get(Table.RUNS, f"execution#{execution_id}")


def claim_run(adapters: Adapters, city: str, requested_by: str) -> dict[str, Any]:
    """Register a run; 409 when one is already in progress for the city."""
    latest = adapters.docstore.get(Table.RUNS, f"run#{city}", "latest")
    if latest and latest["state"] == "running":
        fresh = utc_now() - timedelta(minutes=STALE_RUN_MINUTES)
        if latest["started_at"] > fresh.isoformat():  # older "running" rows are crashed runs
            raise ConflictError(f"a run is already in progress for '{city}'", details=latest)
    doc: dict[str, Any] = {
        "execution_id": new_uuid(),
        "city": city,
        "state": "running",
        "started_at": utc_now().isoformat(),
        "requested_by": requested_by,
        "steps": [],
        "error": None,
    }
    adapters.docstore.put(
        Table.RUNS, f"execution#{doc['execution_id']}", "-", doc, ttl_s=30 * 86400
    )
    adapters.docstore.put(Table.RUNS, f"run#{city}", "latest", doc)
    return doc


def _finish(adapters: Adapters, doc: dict[str, Any], **update: Any) -> dict[str, Any]:
    doc.update(update, finished_at=utc_now().isoformat())
    adapters.docstore.put(
        Table.RUNS, f"execution#{doc['execution_id']}", "-", doc, ttl_s=30 * 86400
    )
    adapters.docstore.put(Table.RUNS, f"run#{doc['city']}", "latest", doc)
    return doc


def run_and_persist(
    settings: AppSettings,
    adapters: Adapters,
    params: ParamRegistry,
    city_slug: str,
    *,
    run_date: date | None = None,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pipeline → persist → forecast → alerts. Returns a summary (also stored on the run doc)."""
    execution = execution or claim_run(adapters, city_slug, "cli")
    try:
        city = load_city(city_slug)
        inputs = CityInputs(city)
        policies = PolicyStore(adapters.docstore)
        pipeline = HeatPipeline(
            city,
            params,
            landsat_source_for(settings, inputs),
            run_date=run_date,
            firms=firms_source_for(settings, inputs),
        )
        run = pipeline.run_all()
        nwp = nwp_source_for(settings, inputs).fetch(
            (city.bbox[1] + city.bbox[3]) / 2,
            (city.bbox[0] + city.bbox[2]) / 2,
            run.params.require_float("P-HD-BOX"),
            int(run.params.require_float("P-HD-HORIZON")),
        )
        imd = policies.get(PolicyType.IMD_HEATWAVE_CRITERIA)
        forecast = forecast_heatdome(nwp, run.params, imd.doc if imd else None).to_dict()
        hub = AlertHub(adapters.docstore, adapters.notifier, run.params)
        transitions = degradation_transitions(adapters.docstore, city.slug, run.trends)
        Repository(adapters.docstore, adapters.blobstore).persist(run, forecast)
        produce_fire_alerts(hub, city.slug, run.fire_events)
        produce_heatdome_alert(hub, city.slug, forecast)
        produce_transition_alerts(hub, city.slug, transitions)
        produce_habitat_alerts(hub, city.slug, [pa.to_dict() for pa in run.habitat])
        top = run.priority.scores[:3]  # type: ignore[union-attr]
        summary = {
            "wards": len(run.contexts),
            "roofs": len(run.roof_contexts),
            "top_wards": [s.ward_id for s in top],
            "heatdome_risk": forecast["risk"],
            "context_version": run.context_version,
        }
        return _finish(adapters, execution, state="succeeded", steps=run.steps, summary=summary)
    except Exception as exc:
        _log.exception("analysis_failed", city=city_slug)
        _finish(adapters, execution, state="failed", error=f"{type(exc).__name__}: {exc}")
        raise
