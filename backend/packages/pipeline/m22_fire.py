"""M22 Satellite fire detection (NASA FIRMS VIIRS + MODIS) → classified, deduplicated events.

Steps: normalise confidence (original kept) → idempotent dedupe → cluster per overpass within the
native pixel scale → classify by WorldCover at the cluster → suppress persistent sources (kilns,
flares) → alert rule (high-confidence vegetation fire within ``P-FIRE-RADIUS`` of a ward, hospital
or protected area). Detections show "last satellite pass", never "now".
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point

from packages.core.enums import FireClass, FireConfidence
from packages.core.errors import UpstreamError
from packages.core.ids import fire_dedupe_key
from packages.core.params import ParamRegistry
from packages.pipeline.grid import Grid
from packages.pipeline.landcover import WorldCover

__all__ = [
    "FireEvent",
    "FirmsFixtureSource",
    "FirmsLiveSource",
    "FirmsSource",
    "detect_fires",
    "normalise_confidence",
]

FIRMS_AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_PRODUCTS = ("VIIRS_SNPP_NRT", "MODIS_NRT")
LAST_PASS_NOTE = "last satellite pass, not real time"


# ------------------------------------------------------------------------------- sources
class FirmsSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, bbox: tuple[float, float, float, float], days: int) -> pd.DataFrame:
        """FIRMS area-API CSV rows for the bbox (lon0, lat0, lon1, lat1)."""


class FirmsFixtureSource(FirmsSource):
    name = "fixture_firms"

    def __init__(self, path: Path | None) -> None:
        self._path = path

    def fetch(self, bbox: tuple[float, float, float, float], days: int) -> pd.DataFrame:
        if self._path is None:
            return pd.DataFrame()
        return pd.read_csv(self._path, dtype={"acq_time": str, "confidence": str})


class FirmsLiveSource(FirmsSource):
    """FIRMS area API (needs a free MAP_KEY). Failures raise ``UpstreamError`` (502)."""

    name = "nasa_firms"

    def __init__(self, map_key: str, timeout_s: float = 30.0) -> None:
        self._key = map_key
        self._timeout = timeout_s

    def fetch(self, bbox: tuple[float, float, float, float], days: int) -> pd.DataFrame:
        area = ",".join(f"{v:.4f}" for v in bbox)
        frames = []
        for product in FIRMS_PRODUCTS:
            url = f"{FIRMS_AREA_URL}/{self._key}/{product}/{area}/{min(max(days, 1), 10)}"
            try:
                res = httpx.get(url, timeout=self._timeout)
                res.raise_for_status()
            except httpx.HTTPError as exc:
                raise UpstreamError(f"FIRMS request failed: {exc}") from exc
            if res.text.strip():
                frame = pd.read_csv(io.StringIO(res.text), dtype={"acq_time": str})
                if "instrument" not in frame:
                    frame["instrument"] = "VIIRS" if "VIIRS" in product else "MODIS"
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ------------------------------------------------------------------------------- events
@dataclass
class FireEvent:
    event_id: str
    lat: float
    lon: float
    acq_date: str
    acq_time: str
    instrument: str
    confidence: FireConfidence
    confidence_raw: str
    frp_mw: float
    n_detections: int
    fire_class: FireClass
    landcover: int | None
    ward_id: str | None = None
    protected_area_id: str | None = None
    alert: bool = False
    severity: str | None = None
    alert_reasons: list[str] = field(default_factory=list)
    note: str = LAST_PASS_NOTE

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["confidence"] = self.confidence.value
        d["fire_class"] = self.fire_class.value
        return d


def normalise_confidence(raw: object, instrument: str) -> FireConfidence:
    """VIIRS: l/n/h letters; MODIS: 0-100 (<30 low, <80 nominal, else high) [R: FIRMS docs]."""
    text = str(raw).strip().lower()
    if text in ("l", "low"):
        return FireConfidence.LOW
    if text in ("n", "nominal"):
        return FireConfidence.NOMINAL
    if text in ("h", "high"):
        return FireConfidence.HIGH
    try:
        value = float(text)
    except ValueError:
        return FireConfidence.LOW
    return (
        FireConfidence.LOW
        if value < 30
        else FireConfidence.NOMINAL
        if value < 80
        else FireConfidence.HIGH
    )


def _components(xy: NDArray[np.float64], radius: float) -> NDArray[np.int64]:
    """Connected components of points closer than ``radius`` (union-find)."""
    n = len(xy)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in cKDTree(xy).query_pairs(radius):
        parent[find(a)] = find(b)
    return np.array([find(i) for i in range(n)])


_CONF_RANK = {FireConfidence.LOW: 0, FireConfidence.NOMINAL: 1, FireConfidence.HIGH: 2}


def _severity(fire_class: FireClass, distance_m: float, frp: float) -> str:
    """Config lookup: class × proximity × FRP band."""
    base = 2 if fire_class is FireClass.FOREST_FIRE else 1
    near = 1 if distance_m <= 1000 else 0
    band = 1 if frp >= 10 else 0
    score = base + near + band
    return "high" if score >= 4 else "medium" if score >= 3 else "low"


def detect_fires(
    raw: pd.DataFrame,
    *,
    grid: Grid,
    landcover: NDArray[np.int64] | None,
    wards_utm: gpd.GeoDataFrame,
    ward_ids: list[str],
    protected_areas: gpd.GeoDataFrame | None,
    hospitals: gpd.GeoDataFrame | None,
    params: ParamRegistry,
    as_of: date,
) -> list[FireEvent]:
    """Classified events from raw FIRMS rows. Idempotent: the same input gives the same output."""
    if raw is None or raw.empty:
        return []
    clusters_cfg = params.require("P-FIRE-CLUSTER")
    persist = params.require("P-FIRE-PERSIST")
    radius = params.require_float("P-FIRE-RADIUS")
    alert_conf = FireConfidence(str(params.require("P-FIRE-CONF")))

    df = raw.copy()
    df["acq_time"] = df["acq_time"].astype(str).str.zfill(4)
    df["instrument"] = df["instrument"].astype(str).str.upper()
    df["dedupe_key"] = [
        fire_dedupe_key(r.latitude, r.longitude, str(r.acq_date), r.acq_time, r.instrument)
        for r in df.itertuples()
    ]
    df = df.drop_duplicates("dedupe_key").reset_index(drop=True)
    df["conf"] = [normalise_confidence(r.confidence, r.instrument) for r in df.itertuples()]

    to_utm = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
    df["x"], df["y"] = to_utm.transform(df["longitude"].to_numpy(), df["latitude"].to_numpy())

    # Persistent sources: the same spot detected on ≥ N separate days within the window.
    window_start = as_of - timedelta(days=int(persist["window_days"]))
    dates = pd.to_datetime(df["acq_date"]).dt.date
    persistent = np.zeros(len(df), dtype=bool)
    xy_all = df[["x", "y"]].to_numpy()
    for idx in range(len(df)):
        near = cKDTree(xy_all).query_ball_point(xy_all[idx], float(persist["radius_m"]))
        days = {dates[j] for j in near if dates[j] >= window_start}
        persistent[idx] = len(days) >= int(persist["days"])

    pa_utm = protected_areas.to_crs(grid.crs) if protected_areas is not None else None
    hosp_utm = hospitals.to_crs(grid.crs) if hospitals is not None and len(hospitals) else None
    events: list[FireEvent] = []
    for (acq_date, acq_time, instrument), group in df.groupby(
        ["acq_date", "acq_time", "instrument"]
    ):
        scale = float(clusters_cfg["viirs_m"] if instrument == "VIIRS" else clusters_cfg["modis_m"])
        labels = _components(group[["x", "y"]].to_numpy(), scale)
        for label in np.unique(labels):
            sub = group[labels == label]
            x, y = float(sub["x"].mean()), float(sub["y"].mean())
            conf = max((FireConfidence(str(c)) for c in sub["conf"]), key=lambda c: _CONF_RANK[c])
            raw_conf = str(sub.loc[sub["conf"].astype(str) == conf.value, "confidence"].iloc[0])
            lc = None
            if landcover is not None:
                cols, rows = (~grid.transform) * (x, y)
                r, c = int(rows), int(cols)
                if 0 <= r < grid.height and 0 <= c < grid.width:
                    lc = int(landcover[r, c])
            point = Point(x, y)
            ward_id = next(
                (w for w, g in zip(ward_ids, wards_utm.geometry, strict=True) if g.contains(point)),
                None,
            )
            pa_id, in_pa, pa_dist = None, False, float("inf")
            if pa_utm is not None:
                for _, pa in pa_utm.iterrows():
                    d = float(pa.geometry.distance(point))
                    if d < pa_dist:
                        pa_dist, pa_id = d, str(pa.get("pa_id", ""))
                    in_pa = in_pa or pa.geometry.contains(point)
            if bool(persistent[sub.index].any()):
                fclass = FireClass.PERSISTENT_SOURCE
            elif lc in (WorldCover.TREE, WorldCover.SHRUB, WorldCover.GRASS):
                forest = lc in (WorldCover.TREE, WorldCover.SHRUB) and in_pa
                fclass = FireClass.FOREST_FIRE if forest else FireClass.VEGETATION_FIRE
            elif lc == WorldCover.CROPLAND:
                fclass = FireClass.AGRICULTURAL_BURNING_CANDIDATE
            elif lc == WorldCover.BUILT:
                fclass = FireClass.URBAN_THERMAL_ANOMALY_CANDIDATE
            else:
                fclass = FireClass.UNCLASSIFIED
            lon, lat = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(x, y)
            frp = float(sub["frp"].max())
            ev = FireEvent(
                event_id=str(sub["dedupe_key"].iloc[0])[:16],
                lat=round(lat, 5),
                lon=round(lon, 5),
                acq_date=str(acq_date),
                acq_time=str(acq_time),
                instrument=str(instrument),
                confidence=conf,
                confidence_raw=raw_conf,
                frp_mw=round(frp, 1),
                n_detections=len(sub),
                fire_class=fclass,
                landcover=lc,
                ward_id=ward_id,
                protected_area_id=pa_id if pa_dist <= params.require_float("P-PA-BUFFER") else None,
            )
            if fclass in (FireClass.VEGETATION_FIRE, FireClass.FOREST_FIRE) and (
                _CONF_RANK[conf] >= _CONF_RANK[alert_conf]
            ):
                reasons = []
                ward_d = min(float(g.distance(point)) for g in wards_utm.geometry)
                if ward_d <= radius:
                    reasons.append("near_ward")
                if hosp_utm is not None and float(hosp_utm.distance(point).min()) <= radius:
                    reasons.append("near_hospital")
                if pa_dist <= radius:
                    reasons.append("near_protected_area")
                if reasons:
                    nearest = min(ward_d, pa_dist)
                    ev.alert, ev.alert_reasons = True, reasons
                    ev.severity = _severity(fclass, nearest, frp)
            events.append(ev)
    events.sort(key=lambda e: (e.acq_date, e.acq_time, e.event_id))
    return events


def ward_event_counts(
    events: list[FireEvent], ward_ids: list[str], as_of: date, days: int = 30
) -> pd.Series:
    """Fire events per ward in the trailing window (persistent sources excluded)."""
    since = (as_of - timedelta(days=days)).isoformat()
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        if e.ward_id and e.acq_date >= since and e.fire_class is not FireClass.PERSISTENT_SOURCE:
            counts[e.ward_id] += 1
    return pd.Series({w: float(counts[w]) for w in ward_ids}, name="fire_events_30d")
