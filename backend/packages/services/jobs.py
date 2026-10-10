"""Scheduled jobs: fire poll (P-FIRE-POLL), daily heat-dome forecast, staleness flip.

Run by APScheduler locally when ``ENABLE_JOBS=true``, by EventBridge on AWS, or from the CLI
(``python -m scripts.run_jobs fire|heatdome|stale``). Each job is idempotent.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from rasterio.enums import Resampling

from packages.adapters.docstore import Table
from packages.adapters.nwp_source import FixtureNWP, NWPSource, OpenMeteoNWP
from packages.adapters.registry import Adapters
from packages.adapters.scheduler import JobSpec
from packages.core.city import load_city
from packages.core.context import WardContext
from packages.core.enums import ValueClass
from packages.core.envelope import ValueEnvelope
from packages.core.logging import get_logger
from packages.core.params import ParamRegistry
from packages.core.settings import AppSettings
from packages.core.timeutil import utc_now
from packages.pipeline.grid import Grid, warp_to_grid
from packages.pipeline.inputs import CityInputs
from packages.pipeline.m01_location import build_ward_layer
from packages.pipeline.m085_context import flip_stale
from packages.pipeline.m22_fire import (
    FireEvent,
    FirmsFixtureSource,
    FirmsLiveSource,
    FirmsSource,
    detect_fires,
    ward_event_counts,
)
from packages.pipeline.m43_heatdome import forecast_heatdome
from packages.services.alert_producers import produce_fire_alerts, produce_heatdome_alert
from packages.services.m37_alerts import AlertHub
from packages.services.policy_store import PolicyStore, PolicyType
from packages.services.repository import Repository

__all__ = [
    "firms_source_for",
    "nwp_source_for",
    "refresh_fire",
    "refresh_heatdome",
    "register_jobs",
    "stale_flip",
]

_log = get_logger("jobs")


def firms_source_for(settings: AppSettings, inputs: CityInputs) -> FirmsSource:
    key = settings.firms_map_key.get_secret_value() if settings.firms_map_key else None
    if settings.firms_source == "live" and key:
        return FirmsLiveSource(key)
    return FirmsFixtureSource(inputs.firms_path)


def nwp_source_for(settings: AppSettings, inputs: CityInputs) -> NWPSource:
    return OpenMeteoNWP() if settings.nwp_source == "open_meteo" else FixtureNWP(inputs.nwp_path)


def refresh_heatdome(
    adapters: Adapters,
    settings: AppSettings,
    params: ParamRegistry,
    city_slug: str,
    source: NWPSource | None = None,
) -> dict[str, Any]:
    """Daily M43 run: forecast → history → ward patch → staff alert when ≥ elevated."""
    city = load_city(city_slug)
    inputs = CityInputs(city)
    params = city.apply_overrides(params)
    src = source or nwp_source_for(settings, inputs)
    lon = (city.bbox[0] + city.bbox[2]) / 2
    lat = (city.bbox[1] + city.bbox[3]) / 2
    nwp = src.fetch(
        lat, lon, params.require_float("P-HD-BOX"), int(params.require_float("P-HD-HORIZON"))
    )
    imd = PolicyStore(adapters.docstore).get(PolicyType.IMD_HEATWAVE_CRITERIA)
    forecast = forecast_heatdome(nwp, params, imd.doc if imd else None).to_dict()
    repo = Repository(adapters.docstore, adapters.blobstore)
    repo.store_forecast(city_slug, forecast)
    hub = AlertHub(adapters.docstore, adapters.notifier, params)
    produce_heatdome_alert(hub, city_slug, forecast)
    _log.info("heatdome_refreshed", city=city_slug, risk=forecast["risk"])
    return forecast


def refresh_fire(
    adapters: Adapters,
    settings: AppSettings,
    params: ParamRegistry,
    city_slug: str,
    source: FirmsSource | None = None,
) -> list[FireEvent]:
    """FIRMS poll: detect → persist events → patch ``hazards.fire_events_30d`` → staff alerts."""
    city = load_city(city_slug)
    inputs = CityInputs(city)
    params = city.apply_overrides(params)
    src = source or firms_source_for(settings, inputs)
    raw = src.fetch(city.bbox, 10)
    wards = build_ward_layer(city, inputs.wards, inputs.boundary_version)
    grid = Grid.from_bbox_lonlat(city.bbox, city.utm_crs, buffer_km=city.bbox_buffer_km)
    landcover = (
        warp_to_grid(str(inputs.landcover_path), grid, resampling=Resampling.nearest).astype(
            "int64"
        )
        if inputs.landcover_path
        else None
    )
    as_of = (
        pd.to_datetime(raw["acq_date"]).max().date()
        if isinstance(src, FirmsFixtureSource) and raw is not None and not raw.empty
        else date.today()
    )
    facilities = inputs.facilities
    events = detect_fires(
        raw,
        grid=grid,
        landcover=landcover,
        wards_utm=wards.wards_utm,
        ward_ids=wards.ward_ids(),
        protected_areas=inputs.protected_areas,
        hospitals=facilities[facilities["kind"] == "hospital"] if facilities is not None else None,
        params=params,
        as_of=as_of,
    )
    for ev in events:
        adapters.docstore.put(
            Table.ENVIRONMENT,
            f"fire#{city_slug}",
            f"{ev.acq_date}#{ev.acq_time}#{ev.event_id}",
            ev.to_dict(),
        )
    counts = ward_event_counts(events, wards.ward_ids(), as_of)
    repo = Repository(adapters.docstore, adapters.blobstore)
    for wid, n in counts.items():
        doc = repo.ward(city_slug, str(wid))
        ctx = doc["ward_context"]
        env = ValueEnvelope.of(
            int(n),
            ValueClass.DERIVED,
            "nasa_firms (last satellite pass)",
            observed=as_of.isoformat(),
            processed=utc_now().date().isoformat(),
        )
        adapters.docstore.update_paths(
            Table.WARD_CONTEXT,
            f"{city_slug}#{wid}",
            f"ctx#{ctx['context_version']}",
            {"ward_context.hazards.fire_events_30d": env.to_json_dict()},
        )
    hub = AlertHub(adapters.docstore, adapters.notifier, params)
    produce_fire_alerts(hub, city_slug, events)
    _log.info("fire_refreshed", city=city_slug, events=len(events))
    return events


def stale_flip(adapters: Adapters, city_slug: str, today: date | None = None) -> int:
    """M8.5 staleness job: fields past ``stale_after`` become ``stale`` (values kept)."""
    repo = Repository(adapters.docstore, adapters.blobstore)
    changed = 0
    for doc in repo.wards(city_slug):
        ctx = WardContext.model_validate(doc["ward_context"])
        flipped = flip_stale(ctx, today or date.today())
        if flipped is not ctx:
            doc["ward_context"] = flipped.to_doc()
            adapters.docstore.update_paths(
                Table.WARD_CONTEXT,
                f"{city_slug}#{ctx.ward_id}",
                f"ctx#{ctx.context_version}",
                {"ward_context": doc["ward_context"]},
            )
            changed += 1
    return changed


def register_jobs(
    adapters: Adapters, settings: AppSettings, params: ParamRegistry, city_slug: str
) -> None:
    poll = int(params.require_float("P-FIRE-POLL"))
    adapters.scheduler.add(
        JobSpec("fire-poll", interval_minutes=poll),
        lambda: refresh_fire(adapters, settings, params, city_slug),
    )
    adapters.scheduler.add(
        JobSpec("heatdome-daily", cron="30 1 * * *"),
        lambda: refresh_heatdome(adapters, settings, params, city_slug),
    )
    adapters.scheduler.add(
        JobSpec("context-staleness", cron="0 2 * * *"),
        lambda: stale_flip(adapters, city_slug),
    )
