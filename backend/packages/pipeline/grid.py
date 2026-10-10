"""The common analysis grid (city UTM, 30 m) and raster helpers shared by batch modules."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from exactextract import exact_extract
from numpy.typing import NDArray
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.io import DatasetReader, MemoryFile
from rasterio.vrt import WarpedVRT

__all__ = ["FloatArray", "Grid", "warp_to_grid", "zonal_stats"]

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid in a projected CRS."""

    crs: str
    transform: Affine
    width: int
    height: int

    @classmethod
    def from_bbox_lonlat(
        cls,
        bbox: Sequence[float],
        crs: str,
        *,
        resolution_m: float = 30.0,
        buffer_km: float = 0.0,
    ) -> Grid:
        """Grid covering a lon/lat bbox (+ buffer), snapped to the resolution."""
        to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        lon0, lat0, lon1, lat1 = bbox
        xs, ys = to_utm.transform([lon0, lon0, lon1, lon1], [lat0, lat1, lat0, lat1])
        buf = buffer_km * 1000.0
        minx = np.floor((min(xs) - buf) / resolution_m) * resolution_m
        maxx = np.ceil((max(xs) + buf) / resolution_m) * resolution_m
        miny = np.floor((min(ys) - buf) / resolution_m) * resolution_m
        maxy = np.ceil((max(ys) + buf) / resolution_m) * resolution_m
        return cls(
            crs=crs,
            transform=Affine(resolution_m, 0, minx, 0, -resolution_m, maxy),
            width=round((maxx - minx) / resolution_m),
            height=round((maxy - miny) / resolution_m),
        )

    @classmethod
    def from_raster(cls, path: str) -> Grid:
        with rasterio.open(path) as src:
            return cls(str(src.crs), src.transform, src.width, src.height)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def resolution_m(self) -> float:
        return float(self.transform.a)

    @property
    def pixel_area_m2(self) -> float:
        return float(abs(self.transform.a * self.transform.e))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        minx, maxy = self.transform.c, self.transform.f
        return (
            minx,
            maxy - self.height * self.resolution_m,
            minx + self.width * self.resolution_m,
            maxy,
        )

    def pixel_centers(self) -> tuple[FloatArray, FloatArray]:
        cols = np.arange(self.width) + 0.5
        rows = np.arange(self.height) + 0.5
        xs = self.transform.c + cols * self.transform.a
        ys = self.transform.f + rows * self.transform.e
        xx, yy = np.meshgrid(xs, ys)
        return xx.astype(np.float64), yy.astype(np.float64)

    def rasterize_ids(self, gdf: gpd.GeoDataFrame, *, fill: int = -1) -> NDArray[np.int32]:
        """Pixel-centre rasterisation of polygons → row index (``fill`` outside)."""
        shapes = ((geom, i) for i, geom in enumerate(gdf.to_crs(self.crs).geometry))
        return rasterize(
            shapes, out_shape=self.shape, transform=self.transform, fill=fill, dtype="int32"
        )

    def sample(self, array: FloatArray, xs: FloatArray, ys: FloatArray) -> FloatArray:
        """Values at projected points (NaN outside the grid)."""
        inv = ~self.transform
        cols, rows = inv * (xs, ys)  # noqa: RUF100  (affine tuple transform)
        cols = np.floor(np.asarray(cols)).astype(int)
        rows = np.floor(np.asarray(rows)).astype(int)
        inside = (cols >= 0) & (cols < self.width) & (rows >= 0) & (rows < self.height)
        out = np.full(len(cols), np.nan)
        out[inside] = array[rows[inside], cols[inside]]
        return out

    @contextmanager
    def as_dataset(self, array: FloatArray) -> Iterator[DatasetReader]:
        """Wrap an array as an in-memory rasterio dataset (NaN = nodata)."""
        with MemoryFile() as mem:
            with mem.open(
                driver="GTiff",
                height=self.height,
                width=self.width,
                count=1,
                dtype="float64",
                crs=self.crs,
                transform=self.transform,
                nodata=np.nan,
            ) as ds:
                ds.write(array.astype(np.float64), 1)
            with mem.open() as ds:
                yield ds

    def write_geotiff(self, array: FloatArray, *, nodata: float = np.nan) -> bytes:
        """GeoTIFF bytes (for the BlobStore)."""
        with MemoryFile() as mem:
            with mem.open(
                driver="GTiff",
                height=self.height,
                width=self.width,
                count=1,
                dtype="float32",
                crs=self.crs,
                transform=self.transform,
                nodata=nodata,
                compress="deflate",
                tiled=True,
                blockxsize=256,
                blockysize=256,
            ) as ds:
                ds.write(array.astype(np.float32), 1)
            return bytes(mem.read())


def warp_to_grid(
    source: str | DatasetReader,
    grid: Grid,
    *,
    resampling: Resampling = Resampling.bilinear,
    band: int = 1,
    src_nodata: float | None = None,
) -> NDArray[Any]:
    """Read one band reprojected onto ``grid`` (only the needed blocks are read).

    Pixels outside the source come back as the source nodata value.
    """

    def _read(src: DatasetReader) -> NDArray[Any]:
        nodata = src_nodata if src_nodata is not None else src.nodata
        with WarpedVRT(
            src,
            crs=grid.crs,
            transform=grid.transform,
            width=grid.width,
            height=grid.height,
            resampling=resampling,
            src_nodata=nodata,
            nodata=nodata,
        ) as vrt:
            return vrt.read(band)

    if isinstance(source, str):
        with rasterio.open(source) as src:
            return _read(src)
    return _read(source)


def zonal_stats(
    grid: Grid,
    array: FloatArray,
    zones: gpd.GeoDataFrame,
    ops: Sequence[str],
) -> pd.DataFrame:
    """Area-weighted (exact coverage) zonal statistics, one row per zone, in zone order.

    ``ops`` uses exactextract names, e.g. ``mean``, ``median``, ``max``, ``stdev``,
    ``quantile(q=0.9)``, ``sum``, ``count``. NaN pixels are ignored.
    """
    with grid.as_dataset(array) as ds:
        frame = exact_extract(
            ds, zones.to_crs(grid.crs).reset_index(drop=True), list(ops), output="pandas"
        )
    frame = pd.DataFrame(frame).reset_index(drop=True)
    frame.index = zones.index
    return frame
