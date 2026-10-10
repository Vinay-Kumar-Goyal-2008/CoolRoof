# DATA_SOURCES — what each module reads

| Module | Source | Local default | Live switch |
|---|---|---|---|
| M3+4 Landsat | Landsat C2 L2 via STAC (Planetary Computer; USGS S3 on AWS) | fixture scenes | `LANDSAT_SOURCE=planetary_computer` |
| M6/M7/M8 | WorldCover, Copernicus DEM, building footprints, WorldPop | `tests/fixtures/mini_city` | paths in `config/cities/<city>.yaml` |
| M22 Fire | NASA FIRMS area API (VIIRS + MODIS NRT) | fixture CSV | `FIRMS_SOURCE=live` + `FIRMS_MAP_KEY` |
| M23/M24 | yearly hot-season medians (`trend_series`), protected areas (WDPA/OSM) | fixture | city config `trend_series`, `protected_areas` |
| M20 | facilities (hospital / school / cooling_point) GeoJSON | fixture | city config `facilities` |
| M25 Solar | PVGIS, then NASA POWER + pvlib fallback, then cache | fixture PVGIS cells | `SOLAR_SOURCE=live` |
| M43 Forecast | Open-Meteo ensemble + ERA5 archive (temperature only) | fixture ensemble | `NWP_SOURCE=open_meteo` |
| Official warnings | typed in by staff (`POST /admin/official-warnings`) | — | — |
| Policy | `seed/policy/*.json` → DocStore, edit with `PUT /admin/policy` | seeded | — |
| LLM | Anthropic API (local) / Bedrock (AWS) | deterministic engine | `ANTHROPIC_API_KEY` or `BEDROCK_MODEL_ID` |
| TTS | Deepgram (EN), Polly (HI) | silent WAV stub | `DEEPGRAM_API_KEY`, `AWS_REGION` |

Licences to check before real use: building footprints, WorldPop, WDPA (storage terms), Planetary Computer / FIRMS terms.
