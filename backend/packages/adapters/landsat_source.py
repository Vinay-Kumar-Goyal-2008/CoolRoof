"""Landsat Collection 2 Level-2 scene sources (D1, fact F8).

* ``FixtureLandsatSource`` — STAC-style ``item.json`` folders (offline mini city).
* ``PlanetaryComputerSource`` — Microsoft Planetary Computer STAC ``landsat-c2-l2``
  with signed URLs (local default for real cities) [R: verify access terms].
* ``USGSS3Source`` — ``s3://usgs-landsat`` requester-pays via the USGS STAC
  server (AWS runtime, us-west-2) [V F8; asset keys R].

All return ``SceneItem`` objects whose bands carry the scale/offset published in
STAC ``raster:bands`` — processing never hard-codes them.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "LANDSAT_BANDS",
    "BandRef",
    "FixtureLandsatSource",
    "LandsatSource",
    "PlanetaryComputerSource",
    "SceneItem",
    "USGSS3Source",
]

# logical band → STAC asset key (Planetary Computer / USGS naming)
LANDSAT_BANDS: dict[str, str] = {
    "st": "lwir11",
    "st_qa": "qa",
    "qa_pixel": "qa_pixel",
    "blue": "blue",
    "green": "green",
    "red": "red",
    "nir": "nir08",
    "swir1": "swir16",
    "swir2": "swir22",
}


@dataclass(frozen=True)
class BandRef:
    href: str
    scale: float = 1.0
    offset: float = 0.0
    nodata: float | None = None


@dataclass(frozen=True)
class SceneItem:
    scene_id: str
    acquired: datetime
    platform: str
    cloud_cover: float
    bands: dict[str, BandRef] = field(default_factory=dict)

    @property
    def year(self) -> int:
        return self.acquired.year


def _band_ref(asset: dict[str, Any], href: str) -> BandRef:
    rb = (asset.get("raster:bands") or [{}])[0]
    return BandRef(
        href=href,
        scale=float(rb.get("scale", 1.0)),
        offset=float(rb.get("offset", 0.0)),
        nodata=rb.get("nodata"),
    )


def item_from_stac(item: dict[str, Any], resolve_href: Any = lambda h: h) -> SceneItem | None:
    """Parse a STAC item dict; returns None when required assets are missing."""
    assets = item.get("assets", {})
    bands: dict[str, BandRef] = {}
    for logical, key in LANDSAT_BANDS.items():
        if key in assets:
            bands[logical] = _band_ref(assets[key], resolve_href(assets[key]["href"]))
    if not {"st", "qa_pixel"} <= bands.keys():
        return None
    props = item["properties"]
    return SceneItem(
        scene_id=item["id"],
        acquired=datetime.fromisoformat(props["datetime"].replace("Z", "+00:00")),
        platform=str(props.get("platform", "unknown")),
        cloud_cover=float(props.get("eo:cloud_cover", 100.0)),
        bands=bands,
    )


class LandsatSource(ABC):
    name: str

    @abstractmethod
    def search(
        self,
        bbox_lonlat: tuple[float, float, float, float],
        start: date,
        end: date,
        max_cloud: float,
    ) -> list[SceneItem]:
        """Landsat 8/9 L2 scenes intersecting ``bbox`` within [start, end]."""


class FixtureLandsatSource(LandsatSource):
    name = "fixture"

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def search(
        self,
        bbox_lonlat: tuple[float, float, float, float],
        start: date,
        end: date,
        max_cloud: float,
    ) -> list[SceneItem]:
        items: list[SceneItem] = []
        for path in sorted(self._folder.glob("*/item.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            item = item_from_stac(raw, lambda h, base=path.parent: str(base / h))
            if item and start <= item.acquired.date() <= end and item.cloud_cover <= max_cloud:
                items.append(item)
        return items


class PlanetaryComputerSource(LandsatSource):
    name = "planetary_computer"
    STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

    def search(
        self,
        bbox_lonlat: tuple[float, float, float, float],
        start: date,
        end: date,
        max_cloud: float,
    ) -> list[SceneItem]:
        import planetary_computer
        from pystac_client import Client

        client = Client.open(self.STAC_URL, modifier=planetary_computer.sign_inplace)
        search = client.search(
            collections=["landsat-c2-l2"],
            bbox=list(bbox_lonlat),
            datetime=f"{start.isoformat()}/{end.isoformat()}",
            query={
                "eo:cloud_cover": {"lte": max_cloud},
                "platform": {"in": ["landsat-8", "landsat-9"]},
            },
        )
        out = [item_from_stac(it.to_dict()) for it in search.items()]
        return [i for i in out if i is not None]


class USGSS3Source(LandsatSource):
    """USGS STAC server; assets resolve to ``s3://usgs-landsat`` (requester pays)."""

    name = "usgs_s3"
    STAC_URL = "https://landsatlook.usgs.gov/stac-server"

    def search(
        self,
        bbox_lonlat: tuple[float, float, float, float],
        start: date,
        end: date,
        max_cloud: float,
    ) -> list[SceneItem]:
        from pystac_client import Client

        client = Client.open(self.STAC_URL)
        search = client.search(
            collections=["landsat-c2l2-st"],
            bbox=list(bbox_lonlat),
            datetime=f"{start.isoformat()}/{end.isoformat()}",
            query={
                "eo:cloud_cover": {"lte": max_cloud},
                "platform": {"in": ["LANDSAT_8", "LANDSAT_9"]},
            },
        )

        def s3_href(href: str) -> str:
            alt = href.replace("https://landsatlook.usgs.gov/data/", "s3://usgs-landsat/")
            return alt

        out = [item_from_stac(it.to_dict(), s3_href) for it in search.items()]
        return [i for i in out if i is not None]
