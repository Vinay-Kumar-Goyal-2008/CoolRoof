"""M25 fallback: NASA POWER monthly climatology + pvlib transposition → kWh/kWp per month.

Used when PVGIS is unreachable. NASA POWER gives monthly mean daily global horizontal irradiance
(``ALLSKY_SFC_SW_DWN``, kWh/m²/day) and 2 m temperature (``T2M``) [R: verify field names on the
live API]. A representative mid-month day is built with pvlib: hourly horizontal irradiance is the
extraterrestrial profile scaled to the daily total, split with the Erbs model, transposed onto the
tilted plane (Hay–Davies) and de-rated for cell temperature with ``gamma_pdc`` (P-GAMMA).
The result is a *loss-free* baseline like PVGIS ``loss=0``; system losses are applied later.
"""

from __future__ import annotations

import calendar
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pvlib

__all__ = ["monthly_kwh_per_kwp", "nasa_power_monthly"]

POWER_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def nasa_power_monthly(
    lat: float, lon: float, client: httpx.Client | None = None
) -> tuple[list[float], list[float]]:
    """(GHI kWh/m²/day, T2M °C) per month from NASA POWER. Raises on HTTP / shape errors."""
    http = client or httpx.Client(timeout=20.0)
    res = http.get(
        POWER_URL,
        params={
            "parameters": "ALLSKY_SFC_SW_DWN,T2M",
            "community": "RE",
            "latitude": lat,
            "longitude": lon,
            "format": "JSON",
        },
    )
    res.raise_for_status()
    param: dict[str, dict[str, float]] = res.json()["properties"]["parameter"]
    ghi = [float(param["ALLSKY_SFC_SW_DWN"][m]) for m in MONTHS]
    temp = [float(param["T2M"][m]) for m in MONTHS]
    if any(v < 0 for v in ghi):  # NASA uses -999 for missing
        raise ValueError("NASA POWER returned missing values")
    return ghi, temp


def monthly_kwh_per_kwp(
    lat: float,
    lon: float,
    tilt: float,
    azimuth: float,
    ghi_kwh_m2_day: list[float],
    t2m_c: list[float],
    gamma_pdc: float,
) -> list[float]:
    """Monthly energy (kWh per kWp, loss-free) from monthly mean daily GHI."""
    out: list[float] = []
    year = 2021  # a non-leap reference year
    for month in range(1, 13):
        day = pd.Timestamp(year=year, month=month, day=15)
        times = pd.date_range(day, periods=24, freq="h", tz="UTC") + pd.Timedelta(minutes=30)
        # Local solar time ≈ UTC + lon/15 h; shift the profile so the sun peaks near local noon.
        shift = pd.Timedelta(hours=-lon / 15.0)
        local_times = times + shift
        solpos = pvlib.solarposition.get_solarposition(local_times, lat, lon)
        dni_extra = pvlib.irradiance.get_extra_radiation(local_times)
        cos_z = np.clip(np.cos(np.radians(solpos["zenith"].to_numpy())), 0, None)
        ghi_ext = dni_extra.to_numpy() * cos_z
        daily_ext = ghi_ext.sum() / 1000.0  # kWh/m²
        if daily_ext <= 0:
            out.append(0.0)
            continue
        kt = min(ghi_kwh_m2_day[month - 1] / daily_ext, 1.0)
        ghi = pd.Series(ghi_ext * kt, index=local_times)
        zen = solpos["zenith"]
        dec = pvlib.irradiance.erbs(ghi, zen, local_times.dayofyear)
        poa = pvlib.irradiance.get_total_irradiance(
            tilt,
            azimuth,
            zen,
            solpos["azimuth"],
            dni=pd.Series(np.asarray(dec["dni"]), index=local_times).fillna(0.0),
            ghi=ghi,
            dhi=pd.Series(np.asarray(dec["dhi"]), index=local_times).fillna(0.0),
            dni_extra=dni_extra,
            model="haydavies",
            albedo=0.2,
        )["poa_global"].fillna(0.0)
        cell = t2m_c[month - 1] + 0.0256 * poa  # NOCT-style cell temperature
        dc = pvlib.pvsystem.pvwatts_dc(poa, cell, pdc0=1.0, gamma_pdc=gamma_pdc)  # kW per kWp
        out.append(round(float(dc.sum()) * calendar.monthrange(year, month)[1], 1))
    return out


def fallback_monthly(
    lat: float, lon: float, tilt: float, azimuth: float, gamma_pdc: float, client: Any = None
) -> list[float]:
    ghi, temp = nasa_power_monthly(lat, lon, client)
    return monthly_kwh_per_kwp(lat, lon, tilt, azimuth, ghi, temp, gamma_pdc)
