"""Generate the synthetic "mini city" fixture (spec §9) deterministically.

Everything here is SYNTHETIC test data with planted, known answers:

* 12 wards (4 × 3 grid of 1.5 km squares) with distinct heat archetypes,
  one sparse-footprint ward (W09 → buildings_incomplete) and an episodic ward (W08).
* Land cover (WorldCover classes), DEM, population grid.
* 3 Landsat-like L2 scenes stored as STAC-style items with ``raster:bands``
  scale/offset, QA_PIXEL bits, ST_QA uncertainty; scene 2 has a cloud patch.
* ~500 building footprints, facilities, a protected forest area.
* Yearly NDVI/BSI/LST series with planted trends, FIRMS sample, NWP ensemble
  with a planted heat-dome event, PVGIS-like solar responses.

Run:  uv run poe fixtures
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from scipy import ndimage
from shapely.geometry import Point, box

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mini_city"
SEED = 20261010
CRS_UTM = "EPSG:32643"
DATASET_ID = "mini_city_synthetic_v1"

# Grid: 300 × 300 pixels at 30 m → 9 km × 9 km
RES = 30.0
NX = NY = 300
X0, Y0 = 373_500.0, 2_052_500.0  # top-left corner (UTM 43N, near Pune)
TRANSFORM = from_origin(X0, Y0, RES, RES)

# City core: 4 × 3 wards of 1.5 km
WARD_SIZE = 1500.0
CORE_X0, CORE_Y0 = 375_000.0, 2_050_250.0  # top-left of ward W01

# WorldCover class codes [R]
TREE, GRASS, CROP, BUILT, BARE, WATER = 10, 30, 40, 50, 60, 80

# Landsat C2 L2 scale/offset as published in STAC raster:bands [R].
ST_SCALE, ST_OFFSET = 0.00341802, 149.0
SR_SCALE, SR_OFFSET = 0.0000275, -0.2
STQA_SCALE = 0.01

# QA_PIXEL bit positions [R: Landsat C2 L2 guide]
BIT_FILL, BIT_DILATED, BIT_CIRRUS, BIT_CLOUD, BIT_SHADOW, BIT_SNOW = 0, 1, 2, 3, 4, 5


@dataclass(frozen=True)
class WardSpec:
    ward_id: str
    name_en: str
    name_hi: str
    fractions: dict[int, float]  # land-cover class → share
    heat_bump_k: float  # persistent extra surface heat
    footprint_completeness: float  # share of expected footprints present
    bldg_size: tuple[float, float]  # m² range


def _hi(n: int) -> str:
    return f"वार्ड {n}"


WARDS: list[WardSpec] = [
    WardSpec(
        "W01",
        "Ward 1 Old Market",
        _hi(1),
        {BUILT: 0.86, TREE: 0.04, GRASS: 0.05, BARE: 0.05},
        1.5,
        1.0,
        (60, 220),
    ),
    WardSpec(
        "W02",
        "Ward 2 Station",
        _hi(2),
        {BUILT: 0.78, TREE: 0.06, GRASS: 0.08, BARE: 0.08},
        1.0,
        1.0,
        (60, 260),
    ),
    WardSpec(
        "W03",
        "Ward 3 Brick Yards",
        _hi(3),
        {BARE: 0.55, BUILT: 0.25, GRASS: 0.15, TREE: 0.05},
        1.2,
        1.0,
        (300, 1800),
    ),
    WardSpec(
        "W04",
        "Ward 4 Garden Colony",
        _hi(4),
        {TREE: 0.40, BUILT: 0.42, GRASS: 0.18},
        -0.5,
        1.0,
        (120, 400),
    ),
    WardSpec(
        "W05",
        "Ward 5 Lake Side",
        _hi(5),
        {WATER: 0.30, TREE: 0.30, BUILT: 0.25, GRASS: 0.15},
        -1.0,
        1.0,
        (120, 400),
    ),
    WardSpec(
        "W06",
        "Ward 6 New Town",
        _hi(6),
        {BUILT: 0.55, GRASS: 0.20, TREE: 0.12, BARE: 0.13},
        0.3,
        1.0,
        (100, 350),
    ),
    WardSpec(
        "W07",
        "Ward 7 Textile Lanes",
        _hi(7),
        {BUILT: 0.84, BARE: 0.08, GRASS: 0.05, TREE: 0.03},
        1.8,
        1.0,
        (60, 200),
    ),
    WardSpec(
        "W08",
        "Ward 8 Fairground",
        _hi(8),
        {BUILT: 0.45, GRASS: 0.30, TREE: 0.15, BARE: 0.10},
        0.0,
        1.0,
        (100, 350),
    ),
    WardSpec(
        "W09",
        "Ward 9 Settlements",
        _hi(9),
        {BUILT: 0.70, BARE: 0.15, GRASS: 0.10, TREE: 0.05},
        0.8,
        0.2,
        (40, 120),
    ),
    WardSpec(
        "W10",
        "Ward 10 University",
        _hi(10),
        {TREE: 0.45, GRASS: 0.25, BUILT: 0.30},
        -0.8,
        1.0,
        (200, 900),
    ),
    WardSpec(
        "W11",
        "Ward 11 MIDC",
        _hi(11),
        {BARE: 0.45, BUILT: 0.40, GRASS: 0.10, TREE: 0.05},
        1.0,
        1.0,
        (400, 2000),
    ),
    WardSpec(
        "W12",
        "Ward 12 Riverside",
        _hi(12),
        {BUILT: 0.50, CROP: 0.20, TREE: 0.15, GRASS: 0.15},
        0.0,
        1.0,
        (100, 350),
    ),
]
EPISODIC_WARD = "W08"
SPARSE_WARD = "W09"

LST_BY_CLASS_K = {BUILT: 316.5, BARE: 318.0, CROP: 313.0, GRASS: 311.5, TREE: 306.0, WATER: 300.5}
# Surface reflectance by class: blue, green, red, nir, swir1, swir2
SR_BY_CLASS = {
    TREE: (0.03, 0.06, 0.04, 0.36, 0.15, 0.08),
    GRASS: (0.05, 0.08, 0.08, 0.30, 0.22, 0.14),
    CROP: (0.08, 0.11, 0.13, 0.24, 0.30, 0.22),
    BUILT: (0.12, 0.14, 0.16, 0.21, 0.25, 0.22),
    BARE: (0.17, 0.21, 0.26, 0.30, 0.40, 0.33),
    WATER: (0.06, 0.07, 0.04, 0.02, 0.01, 0.01),
}
SR_BANDS = ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7")

SCENES = [
    ("LC09_MINI_20240415", date(2024, 4, 15), "landsat-9", -1.0, False, 5.0),
    ("LC08_MINI_20250418", date(2025, 4, 18), "landsat-8", 0.0, True, 18.0),
    ("LC09_MINI_20260421", date(2026, 4, 21), "landsat-9", 1.5, False, 3.0),
]


# ============================================================================ helpers
def smooth_noise(rng: np.random.Generator, shape: tuple[int, int], sigma: float) -> np.ndarray:
    field = ndimage.gaussian_filter(rng.standard_normal(shape), sigma)
    return (field - field.mean()) / (field.std() + 1e-12)


def pixel_centers() -> tuple[np.ndarray, np.ndarray]:
    xs = X0 + (np.arange(NX) + 0.5) * RES
    ys = Y0 - (np.arange(NY) + 0.5) * RES
    return np.meshgrid(xs, ys)


def ward_boxes() -> dict[str, Any]:
    boxes = {}
    for i, spec in enumerate(WARDS):
        row, col = divmod(i, 4)
        x0 = CORE_X0 + col * WARD_SIZE
        y1 = CORE_Y0 - row * WARD_SIZE
        boxes[spec.ward_id] = box(x0, y1 - WARD_SIZE, x0 + WARD_SIZE, y1)
    return boxes


def write_tif(
    path: Path,
    data: np.ndarray,
    dtype: str,
    nodata: float | None = None,
    transform: Any = TRANSFORM,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": CRS_UTM,
        "transform": transform,
        "tiled": True,
        "blockxsize": 128,
        "blockysize": 128,
        "compress": "deflate",
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)


# ============================================================================ layers
def make_landcover(
    rng: np.random.Generator, boxes: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Land cover and a ward-index raster (−1 outside the city)."""
    xx, yy = pixel_centers()
    ward_idx = np.full((NY, NX), -1, dtype=np.int16)
    for i, spec in enumerate(WARDS):
        minx, miny, maxx, maxy = boxes[spec.ward_id].bounds
        ward_idx[(xx >= minx) & (xx < maxx) & (yy >= miny) & (yy < maxy)] = i

    lc = np.zeros((NY, NX), dtype=np.uint8)
    noise = smooth_noise(rng, (NY, NX), sigma=4)

    def assign(mask: np.ndarray, fractions: dict[int, float]) -> None:
        values = noise[mask]
        order = np.argsort(values)
        classes = np.empty(values.size, dtype=np.uint8)
        start = 0
        # water and trees take the lowest-noise blobs so they form patches
        for cls in sorted(
            fractions, key=lambda c: [WATER, TREE, GRASS, CROP, BARE, BUILT].index(c)
        ):
            n = round(fractions[cls] * values.size)
            classes[order[start : start + n]] = cls
            start += n
        classes[order[start:]] = max(fractions, key=fractions.__getitem__)
        lc[mask] = classes

    for i, spec in enumerate(WARDS):
        assign(ward_idx == i, spec.fractions)
    rural = ward_idx < 0
    assign(rural, {CROP: 0.55, TREE: 0.20, GRASS: 0.15, BARE: 0.05, WATER: 0.05})

    # Protected forest block in the north-east corner (outside the city).
    forest = (xx > 381_600) & (yy > 2_050_700)
    lc[forest] = TREE
    return lc, ward_idx


def make_dem(rng: np.random.Generator) -> np.ndarray:
    xx, yy = pixel_centers()
    slope = 560 + (xx - X0) / 9000 * 25 + (Y0 - yy) / 9000 * 10
    return (slope + 3 * smooth_noise(rng, (NY, NX), 10)).astype(np.float32)


def make_scenes(
    rng: np.random.Generator, lc: np.ndarray, ward_idx: np.ndarray, dem: np.ndarray
) -> None:
    base = np.vectorize(LST_BY_CLASS_K.get)(lc).astype(np.float64)
    bump = np.zeros_like(base)
    for i, spec in enumerate(WARDS):
        bump[ward_idx == i] = spec.heat_bump_k
    lapse = -(dem - dem.mean()) * 0.0065
    static_noise = 0.8 * smooth_noise(rng, lc.shape, 3)
    xx, yy = pixel_centers()

    for scene_id, day, platform, offset_k, cloudy, cloud_cover in SCENES:
        lst = base + bump + lapse + static_noise + offset_k + 0.4 * rng.standard_normal(lc.shape)
        if day.year == 2026:  # episodic ward: hot only in the last scene
            lst[ward_idx == WARDS.index(next(w for w in WARDS if w.ward_id == EPISODIC_WARD))] += (
                6.0
            )

        qa = np.zeros(lc.shape, dtype=np.uint16)
        st_qa_k = 1.2 + 0.3 * np.abs(rng.standard_normal(lc.shape))
        if cloudy:
            cloud = np.hypot(xx - 379_000, yy - 2_047_000) < 700
            shadow = (np.hypot(xx - 379_600, yy - 2_046_500) < 400) & ~cloud
            dilated = ndimage.binary_dilation(cloud, iterations=3) & ~cloud
            qa[cloud] |= 1 << BIT_CLOUD
            qa[dilated] |= 1 << BIT_DILATED
            qa[shadow] |= 1 << BIT_SHADOW
            lst[cloud] = 290.0  # cold cloud tops must be masked out
            st_qa_k[dilated] = 4.5  # above P-STQA → dropped
        fill = np.zeros(lc.shape, dtype=bool)
        fill[:, :4] = True  # scene edge
        qa[fill] = 1 << BIT_FILL

        st_dn = np.clip(np.round((lst - ST_OFFSET) / ST_SCALE), 1, 65535).astype(np.uint16)
        st_dn[fill] = 0
        folder = OUT / "landsat" / scene_id
        write_tif(folder / "ST_B10.tif", st_dn, "uint16", nodata=0)
        write_tif(folder / "QA_PIXEL.tif", qa, "uint16", nodata=1)
        write_tif(
            folder / "ST_QA.tif",
            np.round(st_qa_k / STQA_SCALE).astype(np.int16),
            "int16",
            nodata=-9999,
        )
        for band_i, band in enumerate(SR_BANDS):
            refl = np.vectorize(lambda c, b=band_i: SR_BY_CLASS[c][b])(lc).astype(np.float64)
            refl = refl * (1 + 0.05 * rng.standard_normal(lc.shape))
            sr_dn = np.clip(np.round((refl - SR_OFFSET) / SR_SCALE), 1, 65535).astype(np.uint16)
            sr_dn[fill] = 0
            write_tif(folder / f"{band}.tif", sr_dn, "uint16", nodata=0)

        bands_meta = {"scale": SR_SCALE, "offset": SR_OFFSET, "nodata": 0, "data_type": "uint16"}
        assets = {
            "lwir11": {
                "href": "ST_B10.tif",
                "raster:bands": [
                    {"scale": ST_SCALE, "offset": ST_OFFSET, "nodata": 0, "unit": "kelvin"}
                ],
            },
            "qa_pixel": {"href": "QA_PIXEL.tif", "raster:bands": [{"nodata": 1}]},
            "qa": {
                "href": "ST_QA.tif",
                "raster:bands": [
                    {"scale": STQA_SCALE, "offset": 0, "nodata": -9999, "unit": "kelvin"}
                ],
            },
        }
        for band, name in zip(
            SR_BANDS, ("blue", "green", "red", "nir08", "swir16", "swir22"), strict=True
        ):
            assets[name] = {"href": f"{band}.tif", "raster:bands": [bands_meta]}
        item = {
            "type": "Feature",
            "id": scene_id,
            "collection": "landsat-c2-l2",
            "properties": {
                "datetime": f"{day.isoformat()}T05:20:00Z",
                "platform": platform,
                "eo:cloud_cover": cloud_cover,
                "proj:epsg": 32643,
                "synthetic": True,
            },
            "assets": assets,
        }
        (folder / "item.json").write_text(json.dumps(item, indent=2), encoding="utf-8")


def make_buildings(
    rng: np.random.Generator, lc: np.ndarray, ward_idx: np.ndarray, boxes: dict[str, Any]
) -> gpd.GeoDataFrame:
    xx, yy = pixel_centers()
    built_px = lc == BUILT
    total_built = sum(int((built_px & (ward_idx == i)).sum()) for i in range(len(WARDS)))
    target_total = 520
    rows = []
    for i, spec in enumerate(WARDS):
        cand = np.argwhere(built_px & (ward_idx == i))
        expected = round(target_total * len(cand) / total_built)
        n = max(1, round(expected * spec.footprint_completeness))
        picks = cand[rng.choice(len(cand), size=min(n, len(cand)), replace=False)]
        for r, c in picks:
            area = rng.uniform(*spec.bldg_size)
            aspect = rng.uniform(0.6, 1.6)
            w = np.sqrt(area * aspect)
            h = area / w
            cx = xx[r, c] + rng.uniform(-8, 8)
            cy = yy[r, c] + rng.uniform(-8, 8)
            geom = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            ward_geom = boxes[spec.ward_id]
            geom = geom.intersection(ward_geom)
            rows.append(
                {
                    "geometry": geom,
                    "confidence": round(float(rng.uniform(0.62, 0.98)), 3),
                    "floors": int(rng.choice([1, 2, 3, 4], p=[0.3, 0.35, 0.25, 0.1]))
                    if rng.random() < 0.5
                    else None,
                }
            )
    # tiny artefacts and an exact duplicate to exercise cleaning
    rows.append(
        {"geometry": box(377_000, 2_049_000, 377_003, 2_049_003), "confidence": 0.9, "floors": None}
    )
    rows.append(dict(rows[0]))
    gdf = gpd.GeoDataFrame(rows, crs=CRS_UTM)
    gdf["floors"] = gdf["floors"].astype("Int64")
    return gdf.to_crs("EPSG:4326")


def make_population(rng: np.random.Generator, lc: np.ndarray, ward_idx: np.ndarray) -> None:
    """~100 m population grid (3 × 3 Landsat pixels per cell)."""
    built = (lc == BUILT).astype(np.float64)
    density = np.where(ward_idx >= 0, 1.0, 0.08)
    per_px = built * 33.0 * density + (lc == CROP) * 0.4
    per_px *= 1 + 0.1 * rng.standard_normal(per_px.shape)
    per_px = np.clip(per_px, 0, None)
    cells = per_px.reshape(NY // 3, 3, NX // 3, 3).sum(axis=(1, 3)).astype(np.float32)
    write_tif(
        OUT / "population.tif",
        cells,
        "float32",
        nodata=-1.0,
        transform=from_origin(X0, Y0, RES * 3, RES * 3),
    )


def make_vectors(boxes: dict[str, Any]) -> None:
    wards = gpd.GeoDataFrame(
        [
            {
                "ward_id": s.ward_id,
                "name": s.name_en,
                "name_hi": s.name_hi,
                "geometry": boxes[s.ward_id],
            }
            for s in WARDS
        ],
        crs=CRS_UTM,
    ).to_crs("EPSG:4326")
    wards.to_file(OUT / "wards.geojson", driver="GeoJSON")

    pa = gpd.GeoDataFrame(
        [
            {
                "pa_id": "PA-MINI-1",
                "name": "Mini Forest Sanctuary",
                "designation": "Sanctuary",
                "source": "synthetic",
                "geometry": box(381_600, 2_050_700, 382_500, 2_052_500),
            }
        ],
        crs=CRS_UTM,
    ).to_crs("EPSG:4326")
    pa.to_file(OUT / "protected_areas.geojson", driver="GeoJSON")

    def ward_point(wid: str, fx: float, fy: float) -> Point:
        minx, miny, maxx, maxy = boxes[wid].bounds
        return Point(minx + fx * (maxx - minx), miny + fy * (maxy - miny))

    facilities = []
    for wid, fx, fy in [
        ("W01", 0.5, 0.5),
        ("W04", 0.3, 0.7),
        ("W06", 0.6, 0.4),
        ("W10", 0.5, 0.5),
        ("W12", 0.4, 0.6),
        ("W02", 0.8, 0.2),
    ]:
        facilities.append(
            {"kind": "hospital", "name": f"Hospital {wid}", "geometry": ward_point(wid, fx, fy)}
        )
    for idx, (wid, fx, fy) in enumerate(
        [
            ("W01", 0.2, 0.3),
            ("W02", 0.5, 0.5),
            ("W03", 0.4, 0.4),
            ("W05", 0.6, 0.6),
            ("W06", 0.2, 0.8),
            ("W07", 0.5, 0.3),
            ("W07", 0.7, 0.8),
            ("W08", 0.5, 0.5),
            ("W09", 0.3, 0.3),
            ("W10", 0.2, 0.2),
            ("W11", 0.5, 0.7),
            ("W12", 0.8, 0.3),
        ]
    ):
        facilities.append(
            {"kind": "school", "name": f"School {idx + 1}", "geometry": ward_point(wid, fx, fy)}
        )
    for wid in ["W04", "W10", "W12"]:
        facilities.append(
            {
                "kind": "cooling_point",
                "name": f"Cooling centre {wid}",
                "geometry": ward_point(wid, 0.5, 0.5),
            }
        )
    gpd.GeoDataFrame(facilities, crs=CRS_UTM).to_crs("EPSG:4326").to_file(
        OUT / "facilities.geojson", driver="GeoJSON"
    )


def make_trend_series(rng: np.random.Generator) -> None:
    """Hot-season yearly medians per ward and per protected area, with planted trends."""
    years = list(range(2014, 2027))
    planted = {  # ward: (ndvi slope/yr, bsi slope/yr, lst slope °C/yr)
        "W03": (-0.012, 0.010, 0.15),
        "W11": (-0.010, 0.008, 0.0),
        "W06": (0.0, 0.0, 0.12),
        "PA-MINI-1": (-0.010, 0.0, 0.10),
    }
    base_ndvi = {"W04": 0.45, "W05": 0.40, "W10": 0.50, "PA-MINI-1": 0.62}
    rows = []
    for unit in [w.ward_id for w in WARDS] + ["PA-MINI-1"]:
        ndvi_s, bsi_s, lst_s = planted.get(unit, (0.0, 0.0, 0.0))
        noise = 0.02 if unit == "W12" else 0.004
        for k, year in enumerate(years):
            valid = 0.3 if unit == "W09" and year in (2016, 2019, 2022) else 0.9
            rows.append(
                {
                    "unit_id": unit,
                    "unit_kind": "protected_area" if unit.startswith("PA") else "ward",
                    "year": year,
                    "ndvi": round(
                        base_ndvi.get(unit, 0.28) + ndvi_s * k + noise * rng.standard_normal(), 4
                    ),
                    "bsi": round(0.05 + bsi_s * k + noise * rng.standard_normal(), 4),
                    "lst_c": round(40.0 + lst_s * k + 0.1 * rng.standard_normal(), 3),
                    "valid_frac": valid,
                    "rain_mm": round(650 + 60 * rng.standard_normal(), 1),
                }
            )
    pd.DataFrame(rows).to_parquet(OUT / "trend_series.parquet", index=False)


def make_firms(rng: np.random.Generator) -> None:
    """FIRMS-like VIIRS/MODIS rows (area API CSV columns [R])."""
    from pyproj import Transformer

    to_ll = Transformer.from_crs(CRS_UTM, "EPSG:4326", always_xy=True)

    def ll(x: float, y: float) -> tuple[float, float]:
        lon, lat = to_ll.transform(x, y)
        return round(lat, 5), round(lon, 5)

    rows = []

    def add(x: float, y: float, d: date, t: str, inst: str, conf: str, frp: float) -> None:
        lat, lon = ll(x, y)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "bright_ti4": round(330 + rng.uniform(0, 30), 1),
                "scan": 0.39 if inst == "VIIRS" else 1.0,
                "track": 0.36 if inst == "VIIRS" else 1.0,
                "acq_date": d.isoformat(),
                "acq_time": t,
                "satellite": "N20" if inst == "VIIRS" else "Aqua",
                "instrument": inst,
                "confidence": conf,
                "version": "2.0NRT",
                "bright_ti5": 295.0,
                "frp": frp,
                "daynight": "D",
            }
        )

    d0 = date(2026, 4, 1)
    add(382_000, 2_051_500, d0 + timedelta(days=2), "0812", "VIIRS", "h", 14.2)  # forest, inside PA
    add(
        382_100, 2_051_550, d0 + timedelta(days=2), "0812", "VIIRS", "n", 9.1
    )  # same overpass cluster
    add(382_000, 2_051_500, d0 + timedelta(days=2), "0812", "VIIRS", "h", 14.2)  # exact duplicate
    add(381_300, 2_050_500, d0 + timedelta(days=5), "0754", "VIIRS", "h", 11.0)  # near PA (outside)
    add(
        374_200, 2_044_000, d0 + timedelta(days=6), "0830", "VIIRS", "n", 6.3
    )  # cropland: ag burning
    add(377_200, 2_049_400, d0 + timedelta(days=8), "0812", "VIIRS", "l", 3.1)  # urban candidate
    for k in range(6):  # persistent brick kiln in W03
        add(379_300, 2_049_900, d0 + timedelta(days=3 + 4 * k), "0812", "VIIRS", "n", 5.0)
    add(
        382_200, 2_051_900, d0 + timedelta(days=9), "0530", "MODIS", "85", 20.0
    )  # MODIS numeric conf
    pd.DataFrame(rows).to_csv(OUT / "firms_sample.csv", index=False)


def make_nwp() -> None:
    """Ensemble daily Tmax and box-mean Z500 with a planted heat-dome (days 4–7)."""
    issued = date(2026, 5, 10)
    horizon, members = 10, 20
    rng = np.random.default_rng(SEED + 7)
    clim = []
    for d in range(1, horizon + 1):
        day = issued + timedelta(days=d)
        clim.append(
            {
                "date": day.isoformat(),
                "doy": day.timetuple().tm_yday,
                "tmax_mean_c": 39.0,
                "tmax_p90_c": 42.0,
                "z500_mean_m": 5860.0,
                "z500_std_m": 25.0,
            }
        )
    ens = []
    for m in range(members):
        has_event = m < 15  # 75 % of members
        tmax, z500 = [], []
        for d in range(1, horizon + 1):
            if has_event and 4 <= d <= 7:
                tmax.append(round(44.0 + rng.uniform(0, 1.5), 2))
                z500.append(round(5860.0 + 40.0 + rng.uniform(0, 10), 1))
            else:
                tmax.append(round(39.0 + rng.normal(0, 1.0), 2))
                z500.append(round(5860.0 + rng.normal(0, 10), 1))
        ens.append({"member": m, "tmax_c": tmax, "z500_box_mean_m": z500})
    payload = {
        "synthetic": True,
        "source": "fixture_nwp_ensemble",
        "model_run": f"{issued.isoformat()}T00:00Z",
        "issued_at": f"{issued.isoformat()}T06:00:00Z",
        "lat": 18.52,
        "lon": 73.86,
        "box_deg": 5.0,
        "dates": [(issued + timedelta(days=d)).isoformat() for d in range(1, horizon + 1)],
        "members": ens,
        "climatology": clim,
        "planted_event": {"first_day": 4, "duration": 4, "member_share": 0.75},
    }
    (OUT / "nwp_ensemble.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_solar() -> None:
    """PVGIS-PVcalc-like loss-free monthly yields (kWh/kWp) for fixture cells."""
    shape = np.array([138, 140, 160, 158, 157, 120, 98, 102, 118, 136, 133, 132], dtype=float)
    cells = {
        "18.5,73.8": 1.0,
        "18.5,73.9": 1.0,
        "18.6,73.8": 0.99,
        "19.1,72.9": 0.95,
        "28.6,77.2": 0.97,
        "12.9,77.6": 1.01,
    }
    out = {}
    for cell, factor in cells.items():
        monthly = [round(v * factor, 1) for v in shape]
        out[cell] = {
            "synthetic": True,
            "inputs": {"peakpower": 1, "loss": 0},
            "outputs": {
                "monthly": {"fixed": [{"month": i + 1, "E_m": e} for i, e in enumerate(monthly)]},
                "totals": {"fixed": {"E_y": round(sum(monthly), 1)}},
            },
        }
    (OUT / "solar_pvgis.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    boxes = ward_boxes()
    lc, ward_idx = make_landcover(rng, boxes)
    write_tif(OUT / "worldcover.tif", lc, "uint8", nodata=0)
    dem = make_dem(rng)
    write_tif(OUT / "dem.tif", dem, "float32", nodata=-9999.0)
    make_scenes(rng, lc, ward_idx, dem)
    make_buildings(rng, lc, ward_idx, boxes).to_parquet(OUT / "buildings.parquet")
    make_population(rng, lc, ward_idx)
    make_vectors(boxes)
    make_trend_series(rng)
    make_firms(rng)
    make_nwp()
    make_solar()
    manifest = {
        "synthetic": True,
        "dataset_id": DATASET_ID,
        "seed": SEED,
        "crs": CRS_UTM,
        "planted": {
            "episodic_ward": EPISODIC_WARD,
            "buildings_incomplete_ward": SPARSE_WARD,
            "degradation": {"W03": "strong", "W11": "moderate", "W06": "weak"},
            "heatdome": {"first_day": 4, "duration": 4},
            "cloudy_scene": SCENES[1][0],
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"mini city written to {OUT}")


if __name__ == "__main__":
    main()
