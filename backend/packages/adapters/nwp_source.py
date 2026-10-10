"""Forecast + climatology sources for M43 (heat-dome signal).

* ``FixtureNWP``  – reads the synthetic ensemble JSON (tests, offline demo).
* ``OpenMeteoNWP`` – Open-Meteo ensemble forecast (daily Tmax, members) and ERA5 archive for the
  day-of-year climatology (mean / p90 of Tmax; mean / std of Z500 when available).

Both return the same payload the criteria code consumes (``members``, ``climatology``, ``dates``).
Z500 is optional: when the source has no 500 hPa geopotential (Open-Meteo path today), ``z500_box_mean_m`` is ``None`` and
M43 reports a temperature-only, low-confidence, capped signal instead of guessing.
Open-Meteo field names are [R]; verify against the live API (docs/GAPS.md).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from packages.core.errors import UpstreamError
from packages.core.timeutil import utc_now

__all__ = ["FixtureNWP", "NWPSource", "OpenMeteoNWP"]

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class NWPSource(ABC):
    name: str

    @abstractmethod
    def fetch(
        self, lat: float, lon: float, box_deg: float, horizon_days: int
    ) -> dict[str, Any] | None:
        """Forecast payload or ``None`` when the source is unavailable."""


class FixtureNWP(NWPSource):
    name = "fixture_nwp"

    def __init__(self, path: Path | None) -> None:
        self._path = path

    def fetch(
        self, lat: float, lon: float, box_deg: float, horizon_days: int
    ) -> dict[str, Any] | None:
        if self._path is None or not self._path.exists():
            return None
        data: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        return data


class OpenMeteoNWP(NWPSource):
    name = "open_meteo"

    def __init__(
        self, model: str = "gfs025", timeout_s: float = 30.0, client: httpx.Client | None = None
    ):
        self._model = model
        self._timeout = timeout_s
        self._client = client or httpx.Client(timeout=timeout_s)

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            res = self._client.get(url, params=params)
            res.raise_for_status()
            body: dict[str, Any] = res.json()
            return body
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamError(f"open-meteo request failed: {exc}") from exc

    # ------------------------------------------------------------------ forecast
    def _members(self, body: dict[str, Any]) -> tuple[list[str], list[list[float]]]:
        daily = body["daily"]
        dates = list(daily["time"])
        series = [
            [float(v) if v is not None else float("nan") for v in vals]
            for key, vals in daily.items()
            if key.startswith("temperature_2m_max")
        ]
        return dates, series

    # ------------------------------------------------------------------ climatology
    def climatology(self, lat: float, lon: float, target_dates: list[str]) -> list[dict[str, Any]]:
        """Day-of-year Tmax mean/p90 from ERA5 1991–2020 (±7-day window)."""
        body = self._get(
            ARCHIVE_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": "1991-01-01",
                "end_date": "2020-12-31",
                "daily": "temperature_2m_max",
                "timezone": "UTC",
            },
        )
        times = [date.fromisoformat(t) for t in body["daily"]["time"]]
        tmax = np.array(
            [
                np.nan if v is None else v
                for v in body["daily"][
                    "temperature_2m_max_member00"
                    if "temperature_2m_max_member00" in body["daily"]
                    else "temperature_2m_max"
                ]
            ],
            dtype=float,
        )
        doy = np.array([t.timetuple().tm_yday for t in times])
        out = []
        for d in target_dates:
            target = date.fromisoformat(d).timetuple().tm_yday
            window = np.abs(((doy - target + 183) % 366) - 183) <= 7
            vals = tmax[window & np.isfinite(tmax)]
            out.append(
                {
                    "date": d,
                    "doy": target,
                    "tmax_mean_c": round(float(vals.mean()), 2),
                    "tmax_p90_c": round(float(np.percentile(vals, 90)), 2),
                    "z500_mean_m": None,
                    "z500_std_m": None,
                }
            )
        return out

    # ------------------------------------------------------------------ public
    def fetch(
        self, lat: float, lon: float, box_deg: float, horizon_days: int
    ) -> dict[str, Any] | None:
        try:
            body = self._get(
                ENSEMBLE_URL,
                {
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max",
                    "models": self._model,
                    "forecast_days": horizon_days,
                    "timezone": "UTC",
                },
            )
            dates, tmax = self._members(body)
            clim = self.climatology(lat, lon, dates)
        except (UpstreamError, KeyError):
            return None
        members = [
            {"member": i, "tmax_c": tmax[i], "z500_box_mean_m": None} for i in range(len(tmax))
        ]
        now = utc_now()
        return {
            "synthetic": False,
            "source": f"open_meteo:{self._model}",
            "model_run": now.strftime("%Y-%m-%dT00:00Z"),
            "issued_at": now.isoformat(),
            "lat": lat,
            "lon": lon,
            "box_deg": box_deg,
            "dates": dates,
            "members": members,
            "climatology": clim,
            "z500_available": False,
            "note": "No Z500 climatology wired: temperature-only criterion, low confidence, risk capped at watch",
        }
