"""AWS-only wiring that can be checked without AWS: secret-sourced API keys and the scheduled-job entry point."""

from __future__ import annotations

from typing import Any

import pytest

from packages.adapters.secrets import apply_secret_settings as _with_secret_keys
from packages.api import scheduled
from packages.core.enums import Runtime
from packages.core.settings import AppSettings


class _Secrets:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, name: str) -> str | None:
        return self._values.get(name) or None


def _adapters(values: dict[str, str]) -> Any:
    return _Secrets(values)


def test_aws_runtime_loads_api_keys_from_secrets() -> None:
    s = _with_secret_keys(
        AppSettings(_env_file=None, runtime=Runtime.AWS),
        _adapters({"PLANNER_API_KEY": "p-key", "ADMIN_API_KEY": "a-key"}),
    )
    assert s.planner_api_key and s.planner_api_key.get_secret_value() == "p-key"
    assert s.admin_api_key and s.admin_api_key.get_secret_value() == "a-key"


def test_firms_key_comes_from_secrets_for_the_jobs_lambda() -> None:
    s = _with_secret_keys(
        AppSettings(_env_file=None, runtime=Runtime.AWS), _adapters({"FIRMS_MAP_KEY": "f"})
    )
    assert s.firms_map_key and s.firms_map_key.get_secret_value() == "f"


def test_empty_secret_leaves_admin_disabled_and_explicit_settings_win() -> None:
    s = _with_secret_keys(
        AppSettings(_env_file=None, runtime=Runtime.AWS, planner_api_key="explicit"),  # type: ignore[arg-type]
        _adapters({"PLANNER_API_KEY": "other", "ADMIN_API_KEY": ""}),
    )
    assert s.planner_api_key and s.planner_api_key.get_secret_value() == "explicit"
    assert s.admin_api_key is None


def test_local_runtime_never_reads_secrets() -> None:
    s = AppSettings(_env_file=None, runtime=Runtime.LOCAL)
    assert _with_secret_keys(s, _adapters({"PLANNER_API_KEY": "x"})) is s


def test_scheduled_job_dispatch_and_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduled, "refresh_fire", lambda *a, **k: [1, 2, 3])
    monkeypatch.setattr(scheduled, "refresh_heatdome", lambda *a, **k: {"risk": "watch"})
    monkeypatch.setattr(scheduled, "stale_flip", lambda *a, **k: 4)
    settings = AppSettings(_env_file=None)
    args: Any = (settings, object(), object())
    assert scheduled.run_job({"job": "fire"}, *args)["events"] == 3
    assert scheduled.run_job({"job": "heatdome", "city": "x"}, *args) == {
        "job": "heatdome",
        "city": "x",
        "risk": "watch",
    }
    assert scheduled.run_job({"job": "stale"}, *args)["wards_flipped"] == 4
    with pytest.raises(ValueError, match="unknown job"):
        scheduled.run_job({"job": "nope"}, *args)
