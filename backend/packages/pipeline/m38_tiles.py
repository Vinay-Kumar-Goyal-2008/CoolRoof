"""Tile builder: ΔLST raster → PMTiles (PNG tiles, Web Mercator) for the dashboard layer.

Pure Python (rasterio warp + Pillow + ``pmtiles`` writer): no tippecanoe, GDAL CLI or GTK needed.
The legend range is returned so the UI can print "cooler … hotter than the rural reference".
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from packages.pipeline.grid import FloatArray, Grid

__all__ = ["TileSet", "build_dlst_pmtiles", "colorize"]

TILE = 256
WEB_MERCATOR_MAX = 20037508.342789244

# Blue → pale → orange → red (colour-blind safe enough for a heat ramp, with a legend)
_STOPS = np.array(
    [
        [49, 104, 142],
        [120, 190, 210],
        [245, 240, 200],
        [250, 170, 80],
        [200, 40, 30],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class TileSet:
    data: bytes
    min_zoom: int
    max_zoom: int
    n_tiles: int
    vmin: float
    vmax: float
    bounds_lonlat: tuple[float, float, float, float]


def colorize(values: FloatArray, vmin: float, vmax: float, alpha: int = 175) -> NDArray[np.uint8]:
    """RGBA from the ramp; NaN → fully transparent."""
    t = np.clip((values - vmin) / (vmax - vmin), 0, 1)
    pos = np.nan_to_num(t * (len(_STOPS) - 1))
    lo = np.floor(pos).astype(int).clip(0, len(_STOPS) - 2)
    frac = (pos - lo)[..., None]
    rgb = _STOPS[lo] * (1 - frac) + _STOPS[lo + 1] * frac
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.nan_to_num(rgb).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(values), alpha, 0)
    return rgba


def _tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    size = 2 * WEB_MERCATOR_MAX / (2**z)
    minx = -WEB_MERCATOR_MAX + x * size
    maxy = WEB_MERCATOR_MAX - y * size
    return (minx, maxy - size, minx + size, maxy)


def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def build_dlst_pmtiles(
    grid: Grid,
    dlst_c: FloatArray,
    *,
    min_zoom: int = 10,
    max_zoom: int = 14,
    max_tiles: int = 600,
) -> TileSet:
    """PMTiles archive of ΔLST (colour-ramped PNG). Colour range = 2nd–98th percentile."""
    finite = dlst_c[np.isfinite(dlst_c)]
    if finite.size == 0:
        raise ValueError("no finite ΔLST values to tile")
    vmin, vmax = (float(v) for v in np.percentile(finite, [2, 98]))
    if vmax - vmin < 1e-6:
        vmax = vmin + 1.0

    left, bottom, right, top = grid.bounds
    to_ll = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    lon0, lat0 = to_ll.transform(left, bottom)
    lon1, lat1 = to_ll.transform(right, top)
    src_crs = CRS.from_string(grid.crs)
    dst_crs = CRS.from_epsg(3857)

    buf = io.BytesIO()
    writer = Writer(buf)
    tiles: list[tuple[int, bytes]] = []
    for z in range(min_zoom, max_zoom + 1):
        x0, y1 = _lonlat_to_tile(lon0, lat0, z)
        x1, y0 = _lonlat_to_tile(lon1, lat1, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                dst = np.full((TILE, TILE), np.nan, dtype=np.float32)
                reproject(
                    source=dlst_c.astype(np.float32),
                    destination=dst,
                    src_transform=grid.transform,
                    src_crs=src_crs,
                    dst_transform=from_bounds(*_tile_bounds_3857(z, x, y), TILE, TILE),
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                    src_nodata=np.nan,
                    dst_nodata=np.nan,
                )
                if not np.isfinite(dst).any():
                    continue
                png = io.BytesIO()
                Image.fromarray(colorize(dst.astype(np.float64), vmin, vmax), "RGBA").save(
                    png, format="PNG", optimize=True
                )
                tiles.append((zxy_to_tileid(z, x, y), png.getvalue()))
        if len(tiles) > max_tiles:
            raise ValueError(f"tile budget exceeded at zoom {z}: {len(tiles)} > {max_tiles}")
    for tile_id, data in sorted(tiles):
        writer.write_tile(tile_id, data)
    writer.finalize(
        {
            "tile_type": TileType.PNG,
            "tile_compression": Compression.NONE,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "min_lon_e7": int(lon0 * 1e7),
            "min_lat_e7": int(lat0 * 1e7),
            "max_lon_e7": int(lon1 * 1e7),
            "max_lat_e7": int(lat1 * 1e7),
            "center_zoom": (min_zoom + max_zoom) // 2,
            "center_lon_e7": int((lon0 + lon1) / 2 * 1e7),
            "center_lat_e7": int((lat0 + lat1) / 2 * 1e7),
        },
        {
            "name": "dlst",
            "description": "ΔLST vs rural reference (°C), late-morning Landsat surface temperature",
            "vmin": vmin,
            "vmax": vmax,
        },
    )
    return TileSet(
        buf.getvalue(), min_zoom, max_zoom, len(tiles), vmin, vmax, (lon0, lat0, lon1, lat1)
    )
