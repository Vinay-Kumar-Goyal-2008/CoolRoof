"""Helpers shared by the routers."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Query

from packages.api.deps import AppState
from packages.core.errors import NotFoundError
from packages.services.m18_advisory import AdvisoryService, load_advice
from packages.services.m37_alerts import AlertHub
from packages.services.repository import Repository
from packages.services.signals import Signals, current_signals

CityQ = Annotated[str, Query(description="city slug", pattern="^[a-z0-9_]{2,40}$")]
LangQ = Annotated[str, Query(pattern="^(en|hi)$")]


def repo_of(state: AppState) -> Repository:
    return Repository(state.adapters.docstore, state.adapters.blobstore)


def hub_of(state: AppState) -> AlertHub:
    return AlertHub(state.adapters.docstore, state.adapters.notifier, state.params)


def advisories_of(state: AppState) -> AdvisoryService:
    s = state.settings
    return AdvisoryService(
        state.adapters.docstore,
        state.adapters.blobstore,
        state.adapters.tts,
        hub_of(state),
        load_advice(s.rules_dir, s.rules_version),
        two_person_rule=s.advisory_two_person,
        tts_daily_cap=s.tts_daily_cap,
    )


def signals_of(state: AppState, city: str) -> Signals:
    try:
        forecast: dict[str, Any] | None = repo_of(state).manifest(city).get("forecast")
    except NotFoundError:
        forecast = None
    return current_signals(state.adapters.docstore, city, forecast)
