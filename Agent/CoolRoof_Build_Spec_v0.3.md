# CoolRoof Planner + Heat Intelligence + SuryaCheck — Build Spec v0.3

> **For the coding agent (Claude Code).** This file is the single source of truth for building the prototype. It is a condensed rewrite of *Implementation Specification v0.2 (full-build)* plus the v0.3 feature changes listed in §0.2. Read §0 and §1 fully before writing code, then build in the order given in §12.

---

## 0. Read this first

### 0.1 Agent working rules (non-negotiable)

1. **Never invent a value.** No made-up coefficients, prices, tariffs, subsidy figures, thresholds or dataset fields. Every assumption lives in config as a **parameter ID** (§11.4) with status `[ASSUME]`, `[NV]` or `[V]`.
2. **Missing data is `unavailable`, never `0` and never a national default.** Use the fallback in §10.
3. **The LLM never computes numbers.** All numbers come from deterministic functions. The agent explains tool outputs only, and a grounding check enforces this (M33+34).
4. **Every number shown to a user carries provenance.** That means source, date, class badge and assumption IDs.
5. **Ranges, not points,** for anything scenario-based: cool-roof impact, generation, payback and forecasts.
6. **Local-first.** The whole prototype must run with `make dev` on a laptop without AWS credentials (see §2.3), using local adapters for S3, DynamoDB, LLM, TTS and alerts. AWS deployment is a second target that uses the same code.
7. **No Kubernetes.** Use serverless (Lambda, Step Functions) on AWS and `docker compose` locally.
8. **Each module ships with tests** that implement its *Verify* bullets. A module is "done" only when they pass.
9. **Stop and report, don't fake.** If a step needs a credential or an unverified source (marked `[NV]`), build the adapter and a clearly labelled fixture, then list the gap in `docs/GAPS.md`.
10. **Wording rules enforced by tests:**
    - LST is "surface temperature at a late-morning satellite pass", not air temperature.
    - Heat drivers are "associated with", not "caused by".
    - Biodiversity and soil outputs are "indicator", not "loss" or "diagnosis".
    - Forecast heat-dome output is a "forecast signal", not an "official warning".

### 0.2 What changed in v0.3 (vs the uploaded v0.2 doc)

| # | Feature asked for | v0.2 status | v0.3 change |
|---|---|---|---|
| 1 | Heat types per region + info for authorities | M15 (rules + optional GMM) | Kept. Added an authority brief per heat type (§5, M15). |
| 2 | Recommendations: solar, economical cooling, cooling areas, **heat-dome prediction** | M17, M25–32; heat dome was relay-only | **New M43 Heat-Dome / Extreme-Heat Forecast** from open NWP forecasts vs climatology. Added a `cooling_options.json` catalog for locality-based economical cooling (M17 R-EC-01). |
| 3 | Heat tracing (causes) | M16 (correlational) | Kept (still "associated with"). |
| 4 | Public awareness TTS via Deepgram | M18+19 | Kept. Deepgram for English and Amazon Polly for Hindi, because Deepgram TTS has no Hindi voice. |
| 5 | Electricity + hospital recommendations | M20+21 | Kept. Can now also trigger on an M43 forecast (staff-only). |
| 6 | Forest + **normal** fire alerts; biodiversity-loss warnings | M22 satellite only; M23 overlay only | **M22 adds an urban/structure-fire incident path** (staff report + optional fire-service feed) and a heat-linked fire-risk advisory. **M23 upgraded to a Habitat Pressure Index** (tree-cover loss, fire, NDVI and LST trends in protected areas) with change warnings. |
| 7 | Soil degradation | M24 static indicators | **M24 upgraded to yearly tracking** (NDVI, Bare Soil Index, LST, optional rainfall), a Land Degradation Signal and transition alerts. |

### 0.3 Evidence tags

- `[V]` verified against a source in Appendix A
- `[R]` recalled; check the primary doc before relying on it
- `[NV]` needs verification
- `[ASSUME]` modelling assumption exposed as a config parameter

Ward-context value classes are `measured | derived | estimated | policy | user | unavailable | stale`.

### 0.4 Verified facts register

| ID | Fact | Tag |
|---|---|---|
| F1 | PM Surya Ghar residential subsidy is ₹30,000/kW up to 2 kW, plus ₹18,000/kW for additional capacity up to 3 kW. The total is capped at ₹78,000 for systems above 3 kW. | [V] A1, A2 |
| F2 | Suggested size by monthly use: 0–150 units → 1–2 kW; 150–300 → 2–3 kW; >300 → >3 kW | [V] A1 |
| F3 | GHS/RWA: ₹18,000/kW for common facilities incl. EV charging, up to 500 kW (at 3 kW/house), inclusive of individual rooftops | [V] A1, A2 |
| F4 | Applications are made on pmsuryaghar.gov.in | [V] |
| F5 | Subsidy is released after the DISCOM commissioning certificate and bank details, "within 30 days" | [V, secondary] confirm |
| F6 | Eligibility, documents list, vendor and domestic-content rules | [NV] |
| F7 | Net-metering terms are set per state ERC; there is no national table | [NV] |
| F8 | Landsat C2 L1/L2 is in `s3://usgs-landsat`, Requester Pays, us-west-2, with STAC; SNS topic `public-c2-notify-v2` | [V] A4, A5 |
| F9 | Landsat has no use restrictions; attribution is requested | [V] |
| F10 | Deepgram Aura-2 TTS covers EN, ES, DE, FR, NL, IT, JA but **not Hindi** (Hindi is speech-to-text only) | [V] A6, A7 |

---

## 1. System overview

**What it does.** For a city with ward boundaries, the system:

1. Computes hot-season Land Surface Temperature (LST) from Landsat.
2. Joins it with buildings and population.
3. Ranks wards, then buildings, for cool-roof intervention with explicit, configurable scoring.
4. Types and traces each ward's heat.
5. Recommends interventions with evidence.
6. Forecasts heat-dome risk.
7. Issues approved bilingual advisories (text and audio).
8. Alerts on fires and habitat pressure.
9. Tracks land-degradation indicators.
10. Gives homeowners a locality-aware rooftop-solar assessment (PM Surya Ghar subsidy, payback range, Hindi/English agent checklist and PDF).

**Users.**

| User | Needs |
|---|---|
| Municipal planner | Ranked wards and roofs, costs, people protected, action list, recommendations, forecasts |
| Homeowner / RWA | Roof → system size, subsidy, payback range, checklist, PDF |
| Public | Plain-language heat advisories (text and audio), fire alerts |
| Health / emergency / utility officer | Readiness prompts, fire alerts, forecast heat risk |
| Environment / forest officer | Protected-area fire and habitat-pressure warnings, degradation indicators |

**Deterministic vs ML vs LLM.**

- **Deterministic:** LST, zonal stats, scoring, subsidy, generation, payback, PDF, rule engine, heat-dome criteria, trends.
- **ML:** heat-type clustering (2nd opinion), driver attribution (GBM + SHAP), electricity demand (data-gated), roof-type model (optional, data-gated).
- **LLM:** understanding questions, choosing tools, explanation in Hindi/English, checklist guidance, optional tone rewrite.

**Physical caveats (must appear in the UI and PDF):**

- Landsat 8/9 thermal data is acquired late morning, and its native resolution is about 100 m, resampled to 30 m [R]. So LST ≠ air temperature, heat index or night heat, and individual-roof LST cannot be resolved. Roof ranking uses neighbourhood heat plus area, people and cost.
- Definitions:
  - **LST** = surface skin temperature at the satellite pass.
  - **Air temperature / heat index** = from stations or reanalysis, never Landsat.
  - **Surface UHI** = LST − rural reference.
  - **Exposure** = hazard × people (derived).

---

## 2. Architecture

### 2.1 AWS target

```
EXTERNAL                         BATCH (Step Functions)              STORAGE
Landsat C2 L2 (S3 req-pays) ──┐  L-STAC search → L-LST window read,   S3 raw/ curated/ tiles/ models/
Copernicus DEM, ESA WorldCover┤  QA mask, composite → L-FEAT zonal    rules/ audio/ exports/
Buildings (Open Buildings/    ┤  stats → L-CTX Ward Context Builder   DynamoDB: ward_context, roof_context,
 Overture), WorldPop          ┤  Trend job (M24/M23, multi-year)       policy, config, session, cache,
Ward boundaries, OSM POIs     ┤  Heavy raster → Fargate (optional)     alerts, advisories, subscriptions,
PVGIS / NASA POWER (API)      ┤                                        forecasts
NASA FIRMS (API)              ┤  SCHEDULED (EventBridge)
NWP forecast (Open-Meteo/GFS) ┘  FIRMS poller (M22) · Heat-dome forecaster (M43, daily)
                                 Policy freshness (M42) · Staleness job (M8.5)

ANALYSIS (Lambda, deterministic): scoring · roof ranking · cool-roof model · rules engine ·
  solar · subsidy · payback · readiness · habitat pressure · degradation signal
ML (SageMaker Processing, optional): M15 clustering, M16 drivers, M20+21 forecast back-tests

API Gateway (REST) ── Cognito (planner/admin, Phase 2)
  ├─ Amplify frontend (React + MapLibre + PMTiles)
  ├─ Strands Agent (Lambda) → Bedrock model → tools = deterministic APIs
  ├─ PDF Lambda (WeasyPrint container) → S3 presigned URL
  └─ TTS adapter Lambda (Deepgram EN / Polly HI)
Alerts: producers → M37 → SNS (email/SMS) + in-app banner
CloudWatch + AWS Budgets across all
```

Flow classes:

- **Batch** (per city and season): Landsat → LST → features → Ward Context → scores → tiles.
- **Request-time:** solar, subsidy, payback, agent, PDF, recommendations.
- **Scheduled:** FIRMS polling, daily heat-dome forecast, policy freshness, context staleness, yearly trend job.

### 2.2 Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 (backend, pipelines); TypeScript (frontend) |
| Geo | rasterio/GDAL, pystac-client, odc-stac, GeoPandas, shapely 2, exactextract, DuckDB-spatial, h3 |
| Stats/ML | numpy, xarray, scikit-learn, xgboost, shap, statsmodels, pymannkendall, pvlib |
| API | FastAPI app locally; the same handlers on Lambda via Mangum (or Powertools router). pydantic v2 models generate OpenAPI. |
| Agent | Strands Agents SDK. The model provider is Bedrock on AWS, with a pluggable provider locally (Anthropic API / mock) [R, verify SDK providers]. |
| PDF | Jinja2 → HTML → WeasyPrint with Noto Sans + Noto Sans Devanagari |
| Frontend | React + Vite + MapLibre GL + pmtiles + React Query + i18next (en/hi); Playwright tests |
| IaC | AWS CDK (Python) |
| Local infra | `docker compose`: api, frontend, optional MinIO (S3) and DynamoDB Local. A file/SQLite backend is the default. |

### 2.3 Local-first adapters (required)

Every external dependency sits behind an interface with a `local` and an `aws` implementation, selected by the `RUNTIME=local|aws` environment variable.

| Interface | local | aws |
|---|---|---|
| `BlobStore` | `./data/` folder | S3 |
| `DocStore` | SQLite (JSON columns, same PK/SK scheme) | DynamoDB |
| `LLM` | Anthropic API if `ANTHROPIC_API_KEY` is set, else a deterministic mock that calls tools by keyword | Bedrock via Strands |
| `TTS` | Deepgram/Polly if keys exist, else a silent-WAV stub | Deepgram EN / Polly HI |
| `Notifier` | writes to `./data/outbox/*.json` | SNS |
| `Scheduler` | APScheduler in the api process | EventBridge |
| `Landsat source` | Microsoft Planetary Computer STAC (`landsat-c2-l2`, free signed URLs) [R], or cached fixture COGs | `s3://usgs-landsat` requester-pays in us-west-2 |
| `Secrets` | `.env` | Secrets Manager |

---

## 3. Data sources

| ID | Dataset | Use | Resolution / cadence | Access | Licence / notes |
|---|---|---|---|---|---|
| D1 | Landsat C2 L2 (L8/9): ST_B10, ST_QA, QA_PIXEL, SR_B* | LST, NDVI/NDBI/NDWI/BSI | 30 m grid (thermal ~100 m native) [R]; 8-day L8+L9 [R] | STAC + COG, windowed reads | Open, attribution [V] |
| D2 | Ward boundaries | Analysis unit | Vector | Municipal portal / OSM / community GeoJSON [NV] | Varies |
| D3 | Building footprints | Roof area, density | Vector | Google Open Buildings / Overture / MS [R] | Verify licence and India coverage |
| D4 | WorldPop (+ Census 2011 check [NV]) | Population | ~100 m [R] | COG | CC BY [R] |
| D5 | Copernicus DEM GLO-30 | Terrain | 30 m [R] | AWS Open Data COG [R] | Verify |
| D6 | ESA WorldCover | Land cover, reference mask, fire classing | 10 m [R] | AWS Open Data COG [R] | CC BY 4.0 [R] |
| D7 | PVGIS / NASA POWER | PV yield | Climatology | REST | PVGIS free [R]; cache by 0.1° cell |
| D8 | ERA5 / IMD warnings | Context, official warnings | ~25 km [R] / bulletins [NV] | API / manual entry | Verify |
| D9 | OSM hospitals, schools | Infrastructure | Points | Overpass / extracts | ODbL [R] |
| D10 | NASA FIRMS (VIIRS 375 m, MODIS 1 km) | Active fire | NRT, poll 15–60 min | Area API with MAP_KEY [R] | Open |
| D11 | WDPA (fallback OSM `boundary=protected_area`) | Protected areas | Polygons | Query | WDPA redistribution limits [NV] |
| D12 | SoilGrids | SOC, texture | 250 m [R] | COG/WCS | CC BY [R] |
| D13 | PM Surya Ghar policy | Subsidy | Event-driven | Govt pages [V] | Versioned policy record |
| D14 | DISCOM tariff / net metering | Savings | Per order | ERC/DISCOM orders [NV] | Hand-curated |
| D15 | Utility load data | Demand forecast | — | Utility partner only [NV] | Phase 3 data gate |
| **D16 (new)** | **NWP forecast**: daily Tmax, 500 hPa geopotential height (Z500), ensemble members | Heat-dome forecast (M43) | ~0.25° [R]; 7–16 day horizon | Open-Meteo forecast + ensemble API [R], or NOAA GFS / GEFS on AWS Open Data (`noaa-gfs-bdp-pds`) [R] | Verify terms and rate limits |
| **D17 (new)** | **Climatology** for Tmax and Z500 by day-of-year (1991–2020) | M43 anomalies | ~0.25° | ERA5 via Open-Meteo historical API or Copernicus CDS [R] | Compute once per city; cache |
| **D18 (new)** | **Tree-cover loss** (Hansen Global Forest Change) | M23 habitat pressure | 30 m, annual [R] | GCS tiles / GEE export [R] | CC BY 4.0 [R]. Fallback: Landsat NDVI drop inside the WorldCover tree class |
| **D19 (new)** | **Rainfall** (CHIRPS) | M24 rainfall-adjusted trends | ~5 km, daily/monthly [R] | COG/HTTP [R] | Verify |
| **D20 (new, optional)** | **GBIF occurrences** | Species-recorded context in M23 (never "loss") | Points | GBIF API [R] | Per-record licences |
| **D21 (new, optional)** | **Fire-service incident feed** | Urban/structure fires (M22) | Event | City-specific [NV] | Only if permitted |

**Fallbacks when a source is missing:**

- No ward polygons → H3 / 500 m grid with `unit_type: "grid"`.
- No footprints → population-only; roof ranking disabled.
- No DISCOM data → generation and subsidy only, no payback.
- PVGIS down → NASA POWER + pvlib → cached → `unavailable`.
- No NWP source → M43 disabled; relay official warnings only.

---
## 4. Shared contracts (build these first)

### 4.1 Value envelope (every Ward Context field)

```json
"mean_dlst_c": {"value": 3.8, "class": "derived",
  "source": "landsat_c2l2_st; season=2026-MarJun; years=3",
  "observed": "2024-03..2026-06", "processed": "2026-10-07",
  "resolution_m": 30, "confidence": 0.7, "stale_after": "2027-07-01"}
```

### 4.2 Ward Context schema (F = envelope)

```
ward_id, boundary_version, context_version
location:          city, state, centroid, area_km2, unit_type(ward|grid)
heat:              mean_dlst_c, p90_lst_c, persistence, z_vs_city, n_obs, heat_type,
                   top_drivers, drivers_ref,
                   heatdome_risk, heatdome_ref                         # M43 (new)
built_environment: building_count, roof_area_m2, built_fraction, eligible_roof_area_m2
population:        population, density, exposed_population
environment:       ndvi_mean, water_distance_m, elevation_mean_m,
                   ndvi_trend_slope, bsi_trend_slope, lst_trend_slope,  # M24 (bsi/lst new)
                   degradation_signal, bare_fraction, soc_mean
infrastructure:    hospital_count, school_count, cooling_point_count,
                   nearest_hospital_m, facilities_per_10k_exposed
solar:             specific_yield, rooftop_potential_kwp_est
hazards:           fire_events_30d, fire_incidents_30d,                 # incidents new (M22)
                   protected_area_overlap, nearest_protected_area_m,
                   habitat_pressure_max                                 # M23 (new)
administrative:    discom, policy_ref
data_quality:      available, unavailable, estimated, stale, context_confidence (0..1)
```

Only write sections that have at least one available field. Do not create fields without a source. The Roof Context holds `geometry, area, local_heat, pop_b, floors_est?, solar{yield,kWp_max}, intervention{cost,benefit}, policy_ref, ward_ref`.

### 4.3 Who writes what

Only **M8.5** writes whole context versions. **M22, M23 and M43** may make path-limited conditional updates to `hazards.*` and `heat.heatdome_*` on the latest version, because these change faster than a batch run. Other modules write feature tables to `curated/`, and M8.5 reads them on its next build.

### 4.4 Identifiers and enums

- **IDs:**
  - `city` (slug), `ward_id`, `boundary_version`, `context_version` (date-stamped)
  - `building_id = roof_id = hash(dataset_id + geometry)`
  - `run_id` (batch execution)
  - `rules_version` and `templates_version` (immutable S3 prefixes)
  - `policy key = policy#<type>#<state>#<discom>` with SK `effective_date` (national records use `ALL`)
  - `session_id` (128-bit random)
  - `alert_id`, `advisory_id`, `forecast_id` (uuid)
  - fire `dedupe_key = sha1(round(lat,4), round(lon,4), date, time, instrument)`
  - `engine_version`, `input_hash`
- **SolarAssessment field class:** `FACT | ASSUMPTION | USER | ESTIMATE`. **Status:** `complete | partial`.
- **Payback status:** `ok | payback_range_cost_assumed | payback_unavailable_no_tariff | payback_unavailable_stale_tariff | payback_unavailable_unsupported_discom | payback_unavailable_no_consumption`
- **Eligibility:** `unconfirmed | likely | not_eligible_per_answers`
- **Heat type:** `undetermined | not_hot | episodic | dense_built_low_green | open_bare_or_industrial | chronic_other`
- **Suitability:** `suitable | check_obstructions | unsuitable | unknown`
- **Fire class:**
  - satellite: `vegetation_fire (forest_fire) | agricultural_burning_candidate | urban_thermal_anomaly_candidate | unclassified | persistent_source`
  - **incident:** `structure_fire_reported | structure_fire_confirmed` (new)
- **Trend class:** `declining | stable | increasing | insufficient_data | not_applicable`
- **Degradation signal (new):** `none | weak | moderate | strong | insufficient_data | not_applicable`
- **Habitat pressure (new):** `low | moderate | high | insufficient_data`
- **Heat-dome risk (new):** `none | watch | elevated | high | unavailable`
- **Alert / advisory status:** `draft | approved | auto_info | published | sent | suppressed | expired | withdrawn`
- **Other:** `electricity_mode: advisory | forecast`; `unit_type: ward | grid`

### 4.5 API envelope and errors

- Success: `{data, meta:{request_id, context_version, policy_version?, warnings[]}}`
- Error: `{error:{code,message}}`
- Codes:
  - 400 validation
  - 401/403 auth
  - 404 outside coverage
  - 409 run in progress / already approved
  - 422 incomplete or withheld
  - 424 policy missing or stale (only when policy is required)
  - 429 throttled
  - 502 upstream failed with nothing to return
  - 504 timeout (idempotent retry)

---

## 5. Module specs

Each entry gives **Purpose**, **In → Out**, **Logic**, **Edge cases** and **Verify**. "Lambda" means a plain Python function locally. The batch modules form one Step Functions pipeline (a Python orchestrator locally).

### A. Heat-to-priority pipeline (Phase 1)

#### M1+2 Location input and boundary
- **Purpose:** resolve a name, click, address or polygon into `LocationRef {ward_id, city, state, discom, geom, bbox(+1–2 km buffer), centroid, area(UTM)}`.
- **Logic:**
  - Point-in-polygon on wards, then `make_valid` and drop slivers.
  - Store in EPSG:4326 and compute in UTM.
  - Look up state and DISCOM from a curated `city→state→DISCOM` table. If the point is ambiguous or unmapped, ask the user.
- **Edge cases:** point outside wards (404); gaps or overlaps; renumbered wards (store `boundary_version`); names in several scripts.
- **Verify:** every demo centroid falls in exactly one ward; total ward area is within 1–2 % of city area; all geometries are valid.

#### M3+4 Landsat acquisition and preprocessing
- **Inputs:** bbox; season window (default Mar 1–Jun 15, years N, N−1, N−2) [ASSUME]; max scene cloud ≤40 % (scene filter only).
- **Logic:**
  ```
  items = stac_search(bbox, seasons, collections=[landsat-c2l2-st, landsat-c2l2-sr], platforms=[L8,L9])
  for item: windowed read ST_B10, ST_QA, QA_PIXEL, SR bands
    mask = fill|dilated_cloud|cirrus|cloud|shadow|snow (QA_PIXEL bits)
    ST_K = DN*scale + offset   # read scale/offset from STAC raster:bands — never hardcode
    drop pixels with ST_QA uncertainty > P-STQA
    reproject → city UTM, common 30 m grid (bilinear) → raw/ COG chips
  ```
- **Out:** masked ST stack, SR stack, scene manifest (id, date, platform, valid-pixel %).
- **Edge cases:** no clear scene; haze; Landsat 7 mixed in; requester-pays errors.
- **Verify:** valid-pixel % is logged; wards with fewer than `P-MINOBS` observations are flagged `low_confidence`; masks are checked visually on 3 scenes.

#### M5 Land Surface Temperature
- **Method:** use the USGS L2 ST product. Single-channel and split-window methods are rejected. MODIS LST is used only as a cross-check.
- **Logic:** `lst_median = nanmedian(stack)` plus `lst_p90`, `n_obs`, `iqr`, per-year medians and per-scene `hot_flag = LST > city_p90`. Use °C for display only.
- **Verify:**
  - plausible-range filter (% removed is logged)
  - water cooler than built-up
  - r(LST, NDVI) < 0
  - Spearman ρ of ward ranks vs MODIS ≥ `P-MODIS-RHO` [ASSUME]

#### M6 Heat / heat-island analysis
- **Logic:**
  - `ΔLST = LST − median(LST over the rural reference mask)`. The mask is cropland/tree in a 10–20 km ring, excluding water and steep terrain; elevation-adjust using DEM if relief is large.
  - Area-weighted zonal stats per ward (mean, median, p90, max, std).
  - Hotspots: Gi* or percentile + connected components.
  - `persistence_w` = mean share of ward area in the city top decile per scene.
  - `heat_z_w = (ΔLST_w − μ)/σ`.
  - NDVI, NDBI, NDWI and **BSI** from SR.
- **Out:** `heat_features` table; `hotspots.parquet`.
- **Edge cases:** empty reference mask → widen the ring or use a city-percentile baseline (labelled); tiny ward → `ward_too_small`.
- **Verify:** city mean z ≈ 0; hotspots match built/bare/industrial areas; Kendall τ of ranks when one year is left out.

#### M7 Building footprints
- **Logic:** UTM; repair; dedupe; drop below a minimum area; assign ward by centroid. `roof_area` is planimetric [ASSUME flat-equivalent]. Ward aggregates: count, built fraction, roof area, density. Stable `building_id`.
- **Edge cases:** missing buildings in informal areas (sparse wards are flagged `buildings_incomplete` and roof ranking is withheld); merged blobs; no height data.
- **Verify:** built area vs the WorldCover built class (ratio) on 3 wards; precision and recall on about 100 manually checked buildings.

#### M8 Population exposure
- **Logic:**
  ```
  pop_b = Σ_cells pop_cell * area(b∩cell)/Σ_{b'∈cell} area(b')
  ward_pop = Σ pop_b   (scale k_w = official/modelled if an official figure exists, capped)
  exposed_pop_w = Σ_b pop_b * 1[heat_local_b ≥ P-TAU]
  ```
- Vulnerability (age) is `unavailable` unless reliable data exists.
- **Verify:** building sum ≈ grid total (within 1 %); MAPE vs official ward populations; mass-conservation test.

#### M8.5 Ward Context Builder (central)
- **Purpose:** merge all feature tables into one provenance-tagged `ward_context` per ward (and `roof_context`), so no downstream module or the agent reads raw datasets.
- **Logic:**
  - Write envelopes (§4.1).
  - `data_quality` = counts plus `context_confidence` (weighted minimum over critical fields).
  - Conflicting sources → apply a documented precedence and keep `alt_value`.
  - A staleness job flips fields past `stale_after` to `stale`.
- **Storage:** PK `city#ward_id`, SK `ctx#<date>`, plus an S3 snapshot. Items are ≤ 400 KB; larger detail goes to S3 with a pointer.
- **Verify:** 100 % JSON-schema validation; a 10-ward audit tracing each value to its source; removing a dataset yields `unavailable` with no crash and no zero.

#### M9 Ward priority score
- **Normalisation:** within-city percentile pct(·) ∈ [0,1]; use z-score when the city has fewer than about 30 wards.
- **Components:**
  - `H = pct(ΔLST_mean)` (heat intensity)
  - `P = pct(persistence)` (chronic heat)
  - `E = pct(exposed_pop)` (people exposed)
  - `V = 1 − pct(NDVI)` (lack of green)
  - `R = pct(eligible roof area / ward area)` (roof opportunity)
  - `F ∈ [0,1]` (feasibility gate)
- **Formula:**
  ```
  Need = (a_H·H + a_P·P + a_E·E + a_V·V)/Σa ;  Priority = Need·(0.5+0.5·R)·F
  ```
- **Weights (P-W):** equal weights by default; a city profile can be elicited via AHP (stored with author and date); Dirichlet sensitivity (1,000 draws) gives a rank interval and top-10 stability; also leave-one-variable-out. Test the additive alternative.
- **Missing variable:** drop it, renormalise, and record `variables_used` and a lower `score_confidence`. If both heat and population are missing, the ward is unscored.
- **Verify:** hand-computed toy city; monotonicity (raising E never lowers priority); sensitivity report.

#### M10 Roof prioritisation
- **Eligibility filter:** area ≥ minimum, footprint confidence ≥ cutoff, ward not `buildings_incomplete`, rule-based class filters.
- **Score:** `Score_b = f(local_heat_b, pop_b·φ_b, roof_area_b, cost_b)`, i.e. benefit per rupee from M11–13.
- `local_heat_b` is the neighbourhood pixel mean, not the roof's own temperature.
- **Verify:** inspect the top 20 roofs on imagery (% plausible); ranks stay stable under ±20 % cost change.

#### M11+12+13 Cool-roof impact, cost, people protected
- No coefficient is asserted anywhere. All values are scenario triples (low/base/high) from literature [NV] and are calibrated later by a 10–20 roof pilot.
- **Formulas:**
  ```
  f_b = eligible_roof_area_b / pixel_area
  ΔT_pix,b  = P-KCOOL · P-DALB · f_b                 # neighbourhood LST effect (tiny for one roof)
  ΔT_indoor = P-KIND · P-DALB · 1[top floor]
  Cost_b = roof_area_b · P-CM2 · (1 + P-PREP)
  Protected_b = pop_b · φ_b,   φ_b = 1/floors_est_b if known, else P-PHI scenario
  BC_b = Protected_b · heat_weight_b / Cost_b
  Budget: greedy knapsack by BC_b → "cool N roofs for ₹X protecting ~Y people (range)"
  ```
- If `P-CM2` is missing, output benefit only and refuse the BC ratio.
- **Verify:** cost linearity; φ bounds; tornado sensitivity over k, φ and c_m2.

#### M14 Municipal action ranking
- **Logic:** rank wards by Priority, then buildings by BC; apply the budget; attach component breakdowns and warning flags.
- **CSV columns:** `rank, ward, building_id, action, cost_range, people_protected_range, confidence, assumptions`.
- **Verify:** same config and data give an identical list (hash); total cost ≤ budget.

### B. Heat intelligence (Phase 2)

#### M15 Heat-type classification + authority brief
- **Logic:**
  1. **Gate:** if `ndvi_mean`, `built_fraction`, `mean_dlst_c` or `persistence` is unavailable or stale, the type is `undetermined` and the missing fields are listed.
  2. Compute city-relative percentiles.
  3. Apply precedence-ordered rules (first match wins; θ from **P-THETA-HEAT** [ASSUME], defaults q75/q50/q25):

| # | Label | Condition |
|---|---|---|
| 1 | undetermined | required field unavailable or stale |
| 2 | not_hot | pct(ΔLST) < θ_hi |
| 3 | episodic | pct(ΔLST) ≥ θ_hi ∧ pct(persistence) ≤ θ_lo |
| 4 | dense_built_low_green | pct(ΔLST) ≥ θ_hi ∧ pct(built) ≥ θ_hi ∧ pct(NDVI) ≤ θ_lo |
| 5 | open_bare_or_industrial | pct(ΔLST) ≥ θ_hi ∧ pct(built) ≤ θ_mid ∧ pct(NDVI) ≤ θ_lo |
| 6 | chronic_other | pct(ΔLST) ≥ θ_hi and none of 3–5 |

- **Confidence:** `type_confidence = min(feature conf) × margin`, where margin = min over triggering conditions of |pct−θ|/max(θ,1−θ), clipped to [0,1].
- Apply the same rules to hotspot polygons.
- **Optional ML second opinion** (SageMaker Processing): GMM with k=2..6 chosen by BIC (silhouette as tie-break), 200 bootstraps and ARI. Do not publish if ARI < floor. Clusters are named by a human. ML never overwrites rule labels.
- **Authority brief (new):** for each heat type, a template (`rules/<v>/heat_type_briefs.json`) lists what the type means, which M17 rules become eligible, which data to check on the ground and which departments are typically involved. It is rendered per ward with that ward's own values. Text comes from templates and the evidence registry, never from the LLM.
- **Out:** `heat.heat_type`, `type_confidence`, evidence JSON (features, percentiles, thresholds, rules_version, missing[]), typed hotspots, brief.
- **Verify:** synthetic wards for every label and the precedence order (a ward meeting rules 3 and 4 gets 3); θ ± 0.05 flip-rate table; expert review of 10 wards.

#### M16 Heat tracing (driver attribution, correlational)
- **Unit:** N×N pixel blocks (N=3 ≈ native thermal resolution) [ASSUME]; water blocks removed.
- **Features:** NDVI, NDBI, built fraction, roof fraction, distance to water, elevation, slope. Run a VIF filter (NDVI and NDBI are collinear, so keep one or use their first principal component).
- **Models:** OLS (standardised coefficients, robust SE) plus GBM with SHAP. If they disagree on a driver's sign, flag it `unstable`.
- **Validation:** spatial CV by leaving out 2 km tiles with a buffer. Report R², and Moran's I on residuals.
- **Ward attribution:** `contribution_f(w) = mean SHAP_f over the ward's blocks` (°C, direction, bootstrap CI). Outside the training support → `outside_model_support`, no drivers.
- Always attach `unobserved: ["anthropogenic_heat","industrial_process_heat","roof_material"]`.
- **Out:** `drivers[] {feature, contribution_c, direction, ci_low, ci_high, stable}`, model card, `heat.top_drivers` (≤3).
- **Verify:** sign sanity (NDVI −, built +); year-to-year rank stability; expert check on 5 wards. Wording is always "associated with".

#### M17 Recommendation engine (rules, not LLM)
- **Versioned artefacts** (immutable S3 versions): `rules.json`, `evidence.json` (`{id, title, publisher, url, claim, grade A|B|C, context_tags, reviewed_by, reviewed_on}`), **`cooling_options.json` (new)**, and θ parameters.
- **Rule schema:** `{id, intervention, required_fields[], condition, impact_model_ref?, cost_model_ref?, evidence_ref[], evidence_grade, caveats[], audience, excludes[]}`. CI rejects any rule with an empty `evidence_ref`.

| Rule | Intervention | Fires when | Model |
|---|---|---|---|
| R-CR-01 | Ward cool-roof programme | pct(priority) ≥ θ_prio ∧ pct(eligible roof fraction) ≥ θ_roof | M11–13 ranges |
| R-SO-01 | Rooftop solar opportunity → SuryaCheck | pct(solar potential) ≥ θ_sol ∧ roof suitability known | M27+28 ranges |
| R-CP-01 | Public cooling-point siting ("develop cooling areas") | pct(exposed) ≥ θ_exp ∧ few eligible roofs ∧ candidate public facilities exist | qualitative |
| R-EX-01 | Exam / event heat advisory | schools present ∧ hot heat_type ∧ (official warning ∨ M43 ≥ elevated) | qualitative |
| R-GR-01 | Green cover / shade on open land | pct(NDVI) ≤ θ_lo ∧ pct(bare) ≥ θ_bare | qualitative |
| R-RD-01 | Facility readiness → M20+21 | high exposure ∧ (official warning ∨ M43 ≥ elevated) | qualitative |
| R-EC-01 | **Economical cooling options for this locality** | for each `cooling_options.json` entry whose tags (heat_type, built form, roof type, cost band, ownership) all match the ward context | per entry only |
| R-HD-01 | Heat-dome / heatwave relay | official warning active → relay it; else M43 risk ≥ elevated → staff-only "forecast signal" | relay |
| **R-FR-01 (new)** | Heat-linked fire-risk advisory (electrical overload, dry vegetation) | (official warning ∨ M43 ≥ elevated) ∧ (pct(built) ≥ θ_hi ∨ vegetation near wards) | qualitative |
| **R-DG-01 (new)** | Land-degradation field check | `degradation_signal ∈ {moderate, strong}` | qualitative |

- **`cooling_options.json` entry:** `{id, name_i18n, type (passive|active|community), suits{heat_type[], roof_type[], built_form[]}, cost_band (low|med|high), capex_range_inr? [NV], evidence_ref[], caveats}`. Examples to curate from evidence (not asserted): reflective roof paint, shading nets, ventilation, evaporative coolers in dry heat, community cooling centres. Every cost must come from a cited source, otherwise `cost_band` only.
- **Evaluation:**
  - A rule whose required fields are unavailable or stale goes to `not_evaluated` with the missing fields listed.
  - A rule that fires is evaluated through its models, given its evidence, and graded by the minimum grade of its evidence.
  - **Ranking:** Tier 1 = quantified (R-CR-01, R-SO-01), ordered by objective (`benefit_per_cost | people_protected | need`) with ranges. Tier 2 = qualitative, ordered by evidence grade, then the dominant M9 component. Tier 2 never outranks Tier 1. Grade C never enters Tier 1 without an admin override.
- **Out:** `{ward_id, context_version, rules_version, recommendations[], not_evaluated[]}`. Text is template-rendered; the agent may paraphrase but may not add numbers.
- **Evidence intake:** extract entries from the AIDMI extreme-heat resource page and peer-reviewed sources (Appendix B).
- **Verify:** fire / no-fire / missing tests for every rule; counterfactual test (equal LST but different exposure gives different recommendations); byte-identical reproducibility.

#### M18+19 Public awareness + TTS
1. **Compose (deterministic):** choose the template by (advisory type, heat_type, official level or M43 level). Fill slots for ward name, level and validity (quoted with source), plus 1–3 lines drawn only from `advice.json`. Produce EN and HI text.
2. **Optional LLM tone rewrite:** a grounding check confirms all numbers, dates and levels are in the source slots and no advice line is off the whitelist. On failure, keep the template text.
3. **Workflow:** `draft → approved → published → expired | withdrawn`. Only a planner or admin can approve; a two-person rule is configurable. `valid_until` is copied from the warning.
4. **Forecast-based advisories (M43)** default to **staff audience**. Public release needs explicit approval, and the text must say "forecast signal, not an official warning".
5. **TTS adapter:**
   ```python
   provider = "deepgram" if lang=="en" else "polly"     # Deepgram has no Hindi [V F10]
   key = sha256(provider, voice, lang, normalise(text)); cache hit → S3 key
   deepgram: POST /v1/speak model=aura-2-<voice>-en  [V]; polly: hi-IN voice + PLS lexicon [R]
   ```
   If a provider fails, publish text only and log it. Long text is split by sentence; there is a daily synthesis cap.
- **Verify:** template lint; 100 % number grounding; review of 20 Hindi messages by a native speaker; unapproved or expired items are never delivered.

#### M20+21 Hospital / emergency and electricity readiness
- **Hospital half:**
  - Count facilities per ward. `nearest_hospital_m` is measured from the exposed-population-weighted centroid (straight-line by default).
  - `facilities_per_10k_exposed = 10000 · count_within(P-COVER) / exposed_pop`.

| Prompt | Condition | Audience |
|---|---|---|
| HOSP-01 | exposure ≥ θ_exp ∧ (official warning ∨ M43 ≥ elevated) | health officer; "confirm readiness" (never beds or stock) |
| HOSP-02 | exposure ≥ θ_exp ∧ 0 facilities within P-COVER | health officer; coverage gap |
| EXAM-01 | schools ∧ hot type ∧ warning or forecast | exam / event coordinator |
| COOL-01 | cooling_point_count = 0 ∧ high exposure | planner (links to R-CP-01) |
| ELEC-01 | exposure ≥ θ_exp ∧ warning or forecast | utility; "review feeder readiness; no demand data used" |

- **Electricity forecast mode** (Phase 3, data-gated by `electricity_mode=forecast`):
  - Baseline: seasonal-naive.
  - Model: regression of peak demand on **air** temperature (never LST), lags, weekday and holidays.
  - Promote only if rolling-origin MAPE beats the baseline. Output is an uplift range per feeder or ward.
  - Can use M43 forecast Tmax as input.
- **Verify:** spot-check placement of 20 facilities; rule tests; MAPE gate.

#### M22 Fire detection and alerts (forest + normal fires)
- **Satellite path (FIRMS):**
  1. Poll every `P-FIRE-POLL` minutes for the buffered city bbox (VIIRS + MODIS NRT).
  2. Normalise confidence to `low | nominal | high`, keeping the original value.
  3. Idempotent dedupe; cluster per overpass within pixel scale.
  4. Class by WorldCover majority: tree/shrub/grass → `vegetation_fire` (`forest_fire` if tree/shrub majority inside a forest or protected block); cropland → `agricultural_burning_candidate` (info only); built-up → `urban_thermal_anomaly_candidate` (staff info only; weak at 375 m); other → `unclassified`.
  5. Suppress persistent sources (many separate days) such as kilns and flares.
  6. **Alert rule:** high-confidence `vegetation_fire` within `P-FIRE-RADIUS` of a ward, hospital or protected area. Severity = config lookup (class × proximity × FRP band).
- **Incident path (new, for normal / structure fires):**
  - (a) `POST /fire/incidents` lets authenticated staff log a reported fire `{lat, lon, time, type, source, notes}` → `structure_fire_reported`. A second staff confirmation → `structure_fire_confirmed`.
  - (b) An optional `IncidentFeedAdapter` reads a permitted fire-service feed [NV].
  - (c) A satellite urban candidate near a reported incident is linked to it, never auto-confirmed.
  - Public alerts are issued only for confirmed incidents, via M18+19 approval. Each incident is attached to a ward with nearby hospitals and schools.
- **Heat-linked fire risk:** M17 R-FR-01 issues advisories on hot days (above).
- **Context patch:** `hazards.fire_events_30d` and `hazards.fire_incidents_30d`.
- **Edge cases:** latency (show "last satellite pass", not "now"); API down (backoff, alarm, stale banner); WorldCover year mismatch (store `landcover_year`).
- **Verify:** replay one past month (report precision and recall); hand-label about 50 events for false-positive rate; idempotency (two polls give the same count); acq→alert latency metric; incident workflow state tests.

#### M23 Biodiversity: Habitat Pressure Index (Phase 3)
- **Scope:** per protected area (WDPA, or the OSM fallback) and per ward touching it. **It never claims species or biodiversity loss.**
- **Indicators** (yearly, each with significance):

| Indicator | Source | Computation |
|---|---|---|
| I_fire | M22 | vegetation_fire count / burned-cluster area inside + buffer, last 12 months, vs the area's own multi-year mean |
| I_loss | D18 Hansen tree-cover loss (fallback: Landsat NDVI drop > P-VEG-DROP inside the WorldCover tree class) | % of tree area lost in the latest year and cumulative over N years |
| I_veg | M24 trend job | NDVI Sen's slope + Mann–Kendall p within the area |
| I_heat | M5/M24 | LST trend slope within the area |

- **Index:** `HPI = Σ w_i · pct_i`, where pct_i is the percentile of the indicator across all protected areas in the region, or against the area's own history when only one area exists. Weights come from **P-HPI-W** (equal by default [ASSUME]).
- **Classes:** `low | moderate | high` from P-HPI-THETA. `insufficient_data` if fewer than 2 indicators are available.
- **Warnings:**
  - `PA_FIRE_INSIDE` / `PA_FIRE_NEAR` (event-driven).
  - `PA_HABITAT_PRESSURE_RISE` when the class rises versus last year, or I_loss exceeds P-LOSS-ALERT (yearly, to environment and forest officers; not public by default).
- **Optional context:** GBIF species-recorded count and list for the area (D20), shown as "species recorded here", never as a loss count.
- **Message:** names the area, the indicator(s), period and source, and includes "habitat pressure indicator, unverified — not a measured biodiversity loss". A denylist test blocks species-loss wording.
- **Licence:** if WDPA terms block storage, query only or use OSM; if neither is usable, skip the module for that city.
- **Verify:** inside/edge/outside synthetic tests (an edge point counts as inside); index monotonicity; dataset metadata present at 100 %; wording denylist.

#### M24 Land / soil degradation tracking (Phase 3)
- **Trend job** (separate state machine; reuses the M3+4 code): for each hot season from the first L8 year to now (≥ **P-TREND-MIN**, default 8 [ASSUME]), compute per-ward medians over non-built, non-water, cloud-free pixels:
  - `NDVI`
  - `BSI = ((SWIR1+Red) − (NIR+Blue)) / ((SWIR1+Red) + (NIR+Blue))`
  - `LST`

  Use the same sensors (L8/9) every year. If valid coverage < P-COVMIN, mark the year missing.
- **Trends:** Mann–Kendall (with serial-correlation handling) + Sen's slope per indicator, per ward and per protected area.
- **Rainfall adjustment (if D19 is available):** regress NDVI on seasonal rainfall and test the residual trend. Report both raw and adjusted results. Otherwise attach the caveat "vegetation also responds to rainfall".
- **Land Degradation Signal (new):** count the adverse significant trends among {NDVI ↓ (rain-adjusted if possible), BSI ↑, LST ↑}: 0 → `none`, 1 → `weak`, 2 → `moderate`, 3 → `strong`. Fully built wards (> P-BUILT-NA) are `not_applicable`. This aligns conceptually with SDG 15.3.1's productivity sub-indicator [R]; it is not that indicator.
- **Static context:** `bare_fraction` (WorldCover), `soc_mean` and texture (SoilGrids).
- **Tracking:** store the full per-ward yearly series (`curated/soil/series.parquet`) and recompute each season. **Transition alert** (planner-only) when a ward's signal rises by ≥ 1 class versus the last run. Feeds M17 R-DG-01 and M23.
- **Labelling:** every output says "indicator, not diagnosis"; status is `indicator`.
- **Verify:** synthetic series (up, down, flat, noisy) give the expected classes; the class stays the same when one year is dropped (report the share); visual check of 3 wards against historic imagery.

#### M43 (new) Heat-dome / extreme-heat forecast
- **Purpose:** an early "forecast signal" of a heat-dome-like event (persistent upper-level ridge + extreme surface heat) 1–10 days ahead for staff planning. **Official IMD warnings always take precedence and are shown first.**
- **In:** D16 forecast (deterministic + ensemble members: daily Tmax at 2 m, Z500); D17 climatology per day-of-year (mean, std, p90 for Tmax; mean, std for Z500); city centroid; regional box (P-HD-BOX, e.g. ±5°) [ASSUME].
- **Logic** (daily run, scheduled after the forecast update):
  ```
  for member m, day d (1..H):
    T_anom = Tmax[m,d] − clim_mean_T(doy)          ; hotT = Tmax[m,d] ≥ clim_p90_T(doy) and T_anom ≥ P-HD-T
    Z_anom = mean_box(Z500[m,d]) − clim_mean_Z(doy); ridge = Z_anom ≥ P-HD-Z · clim_std_Z(doy)
    signal[m,d] = hotT and ridge
  event[m] = any run of ≥ P-HD-DAYS consecutive signal days
  p_event = share of members with event (deterministic-only → p ∈ {0,1}, flagged low_confidence)
  risk = none | watch (p ≥ P-HD-P1) | elevated (p ≥ P-HD-P2) | high (p ≥ P-HD-P3), with first_day, duration, peak Tmax range (member p10–p90)
  ```
  - Optional IMD-style heatwave check on forecast Tmax with IMD criteria stored as a policy record [R, verify current IMD definitions]. Shown as "meets IMD-style heatwave criterion in forecast", never as an IMD warning.
  - Downscale to wards only as a **relative** modifier: wards are ranked by `heat_z` (M6) to show "where it will likely feel worst". No ward-level temperature is invented.
- **Out:** `forecast` record `{forecast_id, city, issued_at, source, model_run, horizon, risk, p_event, first_day, duration, tmax_range, criteria_params, official_warning_ref?}`; patch `heat.heatdome_risk` / `heatdome_ref`; staff alert via M37 when risk ≥ elevated; triggers M17 (R-HD-01, R-EX-01, R-RD-01, R-FR-01) and M20+21.
- **Storage / AWS:** DynamoDB `forecasts` (PK `city#<slug>`, SK `issued_at`); EventBridge daily Lambda; climatology cached in S3 `curated/climatology/<city>.parquet`.
- **Edge cases:** source down → `unavailable` (never reuse an old forecast as current; show its age); deterministic-only → low confidence; mountain or coastal cities → document box choice; disagreement with official warning → show both, official first.
- **Verify:** hindcast past hot seasons (e.g. the 2022 and 2024 Indian heatwaves [R]) using archived forecasts or reanalysis as perfect-forecast proxy; report hit rate, false-alarm ratio and Brier score; sensitivity of P-HD-* parameters; wording test ("forecast signal").

### C. SuryaCheck (Phase 1)

#### M25 Solar resource
- **Cache key:** `round(lat,1), round(lon,1), tilt, az`.
- **Sources:** PVGIS PVcalc with `peakpower=1, loss=0` (loss-free baseline) [R: verify parameter names and India coverage] → fallback NASA POWER + pvlib → cached cell (labelled stale) → `unavailable`.
- **Scenarios:** `Y_s = Y_0 · (1 − P-LOSS_s)`, applied identically to annual and monthly values. These are the **only** system losses in the pipeline.
- **Out:** `specific_yield{low,base,high}`, `monthly[12]{…}`, meta (source, retrieved_at, cell, assumption IDs).
- **Verify:** PVGIS vs POWER at 5 cities (% difference); plausible-band check; fixture responses.

#### M26 Roof suitability
- **Area:** use the user polygon if given, else the footprint. Recompute area server-side in UTM. Flag `outline_changed` if the ratio exceeds a threshold.
- **Usable area:** `A_usable = A_roof · P-U{low,base,high}`, or the user-stated free area (class USER).
- **Flag:**
  - `suitable` if `A_usable_base / P-AKW ≥ P-KWMIN`
  - `check_obstructions` if the user reports shading or the ward is dense
  - `unsuitable` or `unknown` otherwise
- **Questions for the user:** ownership, roof type, shading, shared roof (→ GHS/RWA path), free area.
- **Verify:** computed vs user free area on 20 homes; area tests in 2 UTM zones; tests for every flag.

#### M27+28 System size and generation
```
kW_area = A_usable / P-AKW ;  kW_load = Σ monthly_kWh / Y_base ;  kW_cap = DISCOM cap [NV, optional]
kW_max = min(...) ; kW_rec = floor(kW_max / P-KWSTEP)·P-KWSTEP (default 1 kW) ; limiting_factor = argmin
Gen_1[s] = kW_rec · Y_s · (1 − P-LID)  (P-LID default 0) ; Gen_t = Gen_1·(1−P-DEG)^(t−1) ; Gen_m from monthly yields
```
- Show the F2 slab guidance alongside, not as a constraint.
- No consumption → return `kW_area` as an upper bound and ask for a bill. Also show the continuous maximum when rounding hides it.
- **Verify:** every limiting branch; property tests (more area never reduces kW_max).

#### M29 PM Surya Ghar subsidy
- The policy is data (DynamoDB `policy#subsidy#ALL#ALL`), not code.
- **Golden fixture:**
  ```
  Residential: S(c) = 30000·min(c,2) + 18000·max(0, min(c,3) − 2)   → 1 kW 30,000 | 2 kW 60,000 | 3 kW 78,000 | 5 kW 78,000
  GHS/RWA:     S = 18000·c (common facilities incl. EV, ≤500 kW at 3 kW/house; cap reading [NV])
  ```
- **State top-up** is a separate record with tri-state `unknown | none_verified | amount`. "Unknown" is never shown as 0.
- **Eligibility:** `unconfirmed` until F6 is verified ("final eligibility is decided on the national portal"). Fractional kW gives an "estimate".
- **Staleness:** age > `P-STALE-POLICY` → warning; age > `P-HARD-POLICY` or inactive → blocks the PDF (424).
- Output always carries `policy_version`, `effective_date`, `source_url`, `rule_id` and the record hash.
- **Verify:** table tests for c ∈ {0.5, 1, 2, 2.5, 3, 3.5, 10}; a stale record blocks the PDF.

#### M30+31 Net metering and payback
- **Records:** tariff (`policy#tariff#<state>#<discom>`: slabs, fixed charge) and settlement (`policy#netmetering#…`: `net_metering | net_billing`, banking, true-up, export rate). Both are hand-curated with `verified_by`.
- **Simulation:**
  ```
  NetCost = Gross − Subsidy − TopUp(amount only)
  monthly sim over H years × {low,base,high}:
    net_metering: net = C − G − bank; billed = max(net,0); bank = max(−net,0)
    net_billing:  self = min(G·s, C); billed = C − self; credit += (G − self)·export_rate
  Savings[t] = (bill_without − bill_with + credits + true_up)·(1+g)^(t−1)
  Payback_simple = NetCost/Savings[1]; Payback_cum = min T: Σ(Savings − O&M − inverter) ≥ NetCost
  ```
- **Headline number** is shown only if the tariff and settlement records are present and fresh, the DISCOM is supported, the gross cost is user-supplied, and consumption is the user's own. Otherwise return the relevant status (§4.4).
- **Arithmetic-only synthetic fixture:** ₹8/kWh flat, full offset, Gross ₹1,50,000, Subsidy ₹78,000, Gen 4,500 kWh, Cons 6,000 kWh, g=d=O&M=0 → NetCost ₹72,000, Savings ₹36,000, payback **2.0 yr**.
- **Verify:** banking edge cases; property tests (higher tariff → shorter payback); 3 real bills per supported DISCOM.

#### M32 SuryaCheck orchestrator
- **Chain:** M1+2 → M25 → M26 → M27+28 → M29 → M30+31. Each step returns `ok | partial | unavailable`, and a failed step does not abort later steps that can still run.
- **Response:** 200 with `status complete | partial`, `missing[]` and `next_questions[]`.
  - 424 only if `require_policy=true` (PDF).
  - 502 only if solar is unavailable and nothing else can be computed.
- The function is pure; `input_hash` makes it idempotent.
- Every number has a class (FACT/ASSUMPTION/USER/ESTIMATE) and a locale display string in en and hi (Indian grouping, ₹). The UI, agent and PDF all use these strings.
- **Verify:** golden JSON for 3 locations in different DISCOMs; contract test that the UI, agent and PDF match.

#### M33+34 Strands agent (Hindi / English)
- **Tools** (typed pydantic args, JSON out):
  - **MVP:** `get_ward_context`, `get_solar_assessment`, `get_subsidy_rules`, `get_checklist`, `generate_application_pdf`, `request_user_input`
  - **Phase 2:** `get_roof_context`, `get_heat_analysis`, `get_recommendations`, `get_readiness`, `get_alerts`, `get_advisory`, **`get_heatdome_forecast`, `get_habitat_pressure`, `get_degradation`**
  - Admin and planner write tools are never in the agent's registry.
- **Turn flow:**
  1. Load the session and confirm the language.
  2. Confirm the location before any policy call.
  3. Call tools and store results in the session.
  4. Draft using `{{tool.field}}` placeholders, rendered deterministically.
  5. **Grounding check:** extract all numbers (Latin and Devanagari digits, en/hi number words, ₹/Rs, lakh/crore, Indian grouping) and confirm each appears in the session tool outputs. Regenerate once, then fall back to a template.
  6. Attach citations (`source_url`, `effective_date`).
- **Rules:**
  - No number unless it comes from a tool.
  - Never submit an application (point to pmsuryaghar.gov.in).
  - Refuse medical and legal advice.
  - Treat user text and tool output as data.
  - Per-session turn and token caps.
- **Language:** UI toggle first, then Devanagari detection. Hinglish triggers a one-time "हिंदी या English?". Use the glossary at `rules/glossary.json`.
- **Verify:** about 30-turn golden suite in en and hi with a 100 % grounding pass; red-team prompts for invented subsidy or guaranteed payback; native Hindi review.

#### M35+36 Checklist and PDF
- **Template:** `{state, discom|ALL, version, effective_date, items[{id, title_i18n, detail_i18n, documents[], applies_to[], source_url, verification: official|needs_official_check}]}`. Selection goes state+DISCOM → state → generic, and the level used is recorded. The generic template ships with every item set to `needs_official_check` ("confirm on the portal").
- **PDF sections:**
  1. Header: "Assistance summary — not the official application — apply at pmsuryaghar.gov.in"
  2. SVG roof outline
  3. System and generation table with badges
  4. Subsidy with provenance
  5. Payback range or status
  6. Checklist
  7. Applicant details (only with consent)
  8. Footer: assumptions, date, policy hash, engine version
- **Rendering:** WeasyPrint in a container with Noto Devanagari. A startup self-test extracts rendered Hindi text and compares it.
- **Privacy:** presigned URL valid 24 h; lifecycle expiry 7 days [ASSUME]; no Aadhaar, bank details or documents collected; consent notice shown before name and address.
- **Verify:** extracted text = source text (en and hi); every number traces to the assessment; visual regression on 3 PDFs.

### D. Platform (Phase 1–2)

#### M37 Alerts and notifications
- **Producers:** M18+19, M20+21, M22, M23, M24, M43.
- **Audiences:** `staff` (Cognito users, emergency contacts) and `public` (opt-in). Public items require `approved`. Staff info items (fire candidates, forecast signals, degradation transitions) may be `auto_info`.
- **SNS:** one topic per city and audience; message attributes `ward_id, language, severity, type` with filter policies; one publish per language.
- **Controls:** dedupe by `alert_id`; rate limit `P-ALERT-RATE` (severity escalation always passes); `valid_until` enforced; DLQ plus an alarm.
- **Subscriptions:** `POST /alerts/subscriptions` (email confirmation; SMS needs sender registration [NV]); addresses stored hashed.
- **In-app:** `GET /alerts?ward=` feeds a banner.
- **Verify:** unapproved or expired public alerts are never sent; filters deliver only the matching ward and language; full audit trail.

#### M38 Dashboard / map (React + MapLibre)
- **Layers:** ΔLST/LST raster (PMTiles), ward priority choropleth, top buildings, hotspots by heat type, facilities, fire events and incidents, protected areas by HPI class, degradation signal, **heat-dome forecast banner and panel**.
- **Screens:**
  1. City / ward picker
  2. Heat map with the LST disclaimer
  3. Ward ranking (component bars, rank interval, confidence)
  4. Ward panel: context, heat type + authority brief, drivers, recommendations, readiness, degradation
  5. Roof list
  6. Roof detail (cool-roof ranges)
  7. SuryaCheck card
  8. Agent chat (EN/हिंदी)
  9. Alerts and forecast
  10. PDF download
  11. Planner console: approve advisories, log fire incidents
- **Provenance UI:** every number has a class badge, with source, date and resolution on hover. Withheld or unavailable states show the reason, never a blank.
- **Basemap:** self-hosted PMTiles (avoid public OSM tile servers).
- **Accessibility:** keyboard-navigable table, colour-blind-safe palette, mobile on-demand tiles.
- **Verify:** Playwright tests for the happy path and unavailable states; demo walkthrough.

#### M39 Backend API
- One router per domain (locations, analysis, wards, solar, agent, documents, alerts, fire, environment, forecast, admin).
- pydantic gives OpenAPI; body size limits; GeoJSON validation; CORS limited to the frontend origin.
- `POST /analysis/heat` starts an execution and returns 202 with an id. The agent route must finish within the API timeout (~29 s [R]), otherwise 504 with an idempotent retry.
- **Verify:** contract tests against OpenAPI; auth matrix tests; idempotency tests.

#### M40 Storage
- **S3 prefixes:** `raw/ curated/ tiles/ models/ rules/ audio/ exports/` with a dataset registry at `curated/_registry/` (name, version, url, licence, retrieved_at, sha256, bbox, resolution).
- **DynamoDB tables** (on-demand, PITR on durable tables):

| Table | PK / SK | Notes |
|---|---|---|
| ward_context / roof_context | `city#ward_id` / `ctx#<v>`, `reco#<ctx>#<rules>`; roof `ward#building_id` | GSI city + priority_rank |
| policy | `policy#<type>#<state>#<discom>` / `<effective_date>` | types: subsidy, subsidy_topup, tariff, netmetering, checklist, **imd_heatwave_criteria** |
| config | `config#<city|global>` / `<type>#<version>` | P-* values, rules pointer, electricity_mode, author + date |
| session | `session#<id>` | TTL |
| cache | `solar#<cell>` / `tts#<hash>` | TTL |
| alerts | `fire#<city>` or `ward#<id>` / `<ts>#<id>` | fire events, **incidents**, audit; GSI status, ward_id |
| advisories | `ward#<id>` / `adv#<id>` | GSI status |
| subscriptions | `ward#<id>` / `sub#<id>` | GSI status |
| **forecasts (new)** | `city#<slug>` / `<issued_at>` | M43 |
| **environment (new)** | `pa#<id>` or `ward#<id>` / `<year>#<indicator>` | M23 HPI and M24 series summaries (detail in S3) |

- Aurora/PostGIS only if spatial SQL outgrows DuckDB (Phase 3).
- Encryption at rest; no PII outside sessions, hashed subscriptions and PDFs.

#### M41 Auth

| Capability | Anon | viewer | planner | admin |
|---|---|---|---|---|
| SuryaCheck, agent, PDF | ✓ | ✓ | ✓ | ✓ |
| Read ward ranking, context, recommendations, forecasts | ✓ [ASSUME] | ✓ | ✓ | ✓ |
| Run analysis, action plan | | | ✓ | ✓ |
| Create / approve advisories and alerts; **log / confirm fire incidents** | | | ✓ | ✓ |
| Edit weights, thresholds, rules pointer | | | | ✓ |
| Edit policy records (verified_by required) | | | | ✓ (MFA) |

- Anonymous sessions use a random 128-bit id with TTL.
- Cognito is Phase 2; the demo uses an API key on planner routes.
- Roles can be scoped to a city. All writes are immutable versions with author and timestamp.

#### M42 Monitoring and evaluation
- **Metrics and alarms:**
  - Batch: scenes, valid %, low-confidence wards, bytes read.
  - API: 5xx, p95.
  - Agent: grounding pass rate, fallback rate, tokens.
  - Policy age.
  - FIRMS poll success, latency, DLQ.
  - Solar fallback share.
  - **M43:** forecast run success, source age.
  - **M24/M23:** trend job coverage.
  - Cost (AWS Budgets).
- **CI gates:** unit and property tests; SuryaCheck golden fixtures; golden agent suite (zero ungrounded numbers); heat-pipeline regression on a fixture city (rank ρ ≥ floor); schema validation; wording denylist tests.
- **Scheduled:** policy-freshness job, synthetic canary on `/solar/assess`.
- **Logs:** structured JSON with `request_id`/`run_id`, no PII.

---
## 6. API endpoints (v1)

| Endpoint | Module | Key response | Errors |
|---|---|---|---|
| `GET/POST /locations/resolve` | M1+2 | LocationRef | 404 |
| `POST /analysis/heat` · `GET /analysis/heat/{id}` | pipeline | execution id / state | 409, 403 |
| `GET /wards?city=&sort=priority` | M9 | wards with components, rank interval | 404 |
| `GET /wards/{id}/context` | M8.5 | ward_context | 404 |
| `GET /wards/{id}/buildings?top=&budget=` | M10 | ranked roofs with ranges | 422 |
| `GET /buildings/{id}/context` | M8.5 | roof_context | 404 |
| `POST /interventions/plan` | M14 | plan + CSV link | 422 |
| `GET /wards/{id}/heat-type` | M15 | type, confidence, evidence, **brief** | 404 |
| `GET /wards/{id}/drivers` | M16 | drivers[], unobserved[], model card | 404, 422 |
| `GET /wards/{id}/recommendations?objective=` | M17 | recommendations[], not_evaluated[] | 404 |
| `GET /cooling-options?ward=` **(new)** | M17 | matched catalog entries with evidence | 404 |
| `POST /advisories` · `POST /advisories/{id}/approve` | M18+19 | draft / approved | 403, 409, 422 |
| `POST /tts` | M18+19 | audio_url | 502 |
| `GET /wards/{id}/readiness` | M20+21 | facilities, distances, prompts[] | 404 |
| `GET /fire/events?bbox=&since=` | M22 | satellite events | 400 |
| `POST /fire/incidents` · `POST /fire/incidents/{id}/confirm` · `GET /fire/incidents?city=` **(new)** | M22 | incident records | 403, 422 |
| `GET /protected-areas?city=` · `GET /protected-areas/{id}/pressure` **(new)** · `GET /protected-areas/alerts?city=` | M23 | HPI, indicators, alerts | 404 |
| `GET /wards/{id}/soil` | M24 | series summary, trends, **degradation_signal**, status: indicator | 404 |
| `GET /forecast/heatdome?city=` · `GET /forecast/heatdome/history?city=` **(new)** | M43 | latest forecast + official warning ref | 404 |
| `POST /solar/assess` | M32 | SolarAssessment | 424, 502 |
| `GET /policy/subsidy?state=&discom=&date=` | M29 | policy record | 404 |
| `GET /checklist?state=&discom=&applicant=` | M35+36 | checklist | 404 |
| `POST /documents/application-pdf` | M35+36 | url, expires_at | 422, 424 |
| `POST /sessions` | M41 | session_id | 429 |
| `POST /agent/chat` | M33+34 | reply, citations[], trace id | 429, 504 |
| `GET /alerts?ward=` · `POST/DELETE /alerts/subscriptions` | M37 | active alerts / subscription | 422, 429 |
| `PUT /admin/policy` · `PUT /admin/config` · `POST /admin/official-warnings` **(new: manual IMD entry)** | M41 | version | 403, 422 |
| `GET /health` | M42 | status, versions | — |

---

## 7. AWS services (what and why)

**MVP:** S3 + Open Data · Lambda (containers for geo and PDF) · Step Functions · DynamoDB · API Gateway (REST) · Amplify · Bedrock + Strands · CloudWatch · Secrets Manager · AWS Budgets.

**Phase 2:** EventBridge Scheduler (FIRMS, M43 daily, freshness, staleness) · SNS (alerts) · Cognito · Amazon Polly (Hindi TTS).

**Optional / scale:**

- SageMaker Processing (M15 clustering, M16 drivers, M20+21 back-tests)
- Fargate (large rasters, trend job)
- Aurora PostGIS
- SQS (DLQ / buffer)
- Amazon Location (routing)
- WAF

**Not used:** Kubernetes / EKS, Glue, EMR, Kinesis, Redshift, OpenSearch.

**Region:** Landsat processing runs in **us-west-2**, next to the bucket. Only small curated outputs are copied to the user-facing region.

## 8. ML summary

| Model | Status | Baseline | Method | Evaluation |
|---|---|---|---|---|
| LST | no ML | USGS L2 product | — | MODIS cross-check |
| Heat-type clustering (M15) | optional 2nd opinion | rule archetypes | GMM | bootstrap ARI, expert review |
| Driver attribution (M16) | Phase 2 | OLS | GBM + SHAP | spatial-CV R², Moran's I |
| Heat-dome forecast (M43) | Phase 2 | deterministic criteria on single run | ensemble exceedance probability (no training) | hindcast hit rate, FAR, Brier |
| Habitat pressure (M23) / degradation (M24) | Phase 3 | indicator thresholds | MK + Sen trends, percentile index | synthetic series, visual checks |
| Electricity demand (M20+21) | Phase 3, data-gated | seasonal naive | regression on air temp | rolling MAPE |
| Roof type | Phase 3, optional | user confirmation | CNN | IoU |
| Agent | yes | template UI | Bedrock via Strands | golden suite, 100 % grounding |

---

## 9. Repo layout (create exactly this)

```
coolroof/
  README.md  Makefile  docker-compose.yml  .env.example  pyproject.toml
  docs/  SPEC.md (this file)  GAPS.md  DEMO.md  DATA_SOURCES.md
  config/
    params.default.yaml        # every P-* ID with value|null, status, source
    cities/<city>.yaml         # bbox, season, UTM EPSG, DISCOM map, weight profile
  rules/v1/  rules.json evidence.json cooling_options.json heat_type_briefs.json
             advice.json templates/{en,hi}/*.j2 glossary.json
  seed/  policy/subsidy_pm_surya_ghar.json (F1/F3, [V])
         policy/tariff_TEST-DISCOM.json (SYNTHETIC, flagged, test-only)
         policy/checklist_generic.json (all needs_official_check)
         policy/imd_heatwave_criteria.json ([R], status needs_verification)
  packages/
    core/        envelope, ids, enums, errors, params registry, provenance, grounding lib, i18n formatters
    adapters/    blobstore, docstore, llm, tts, notifier, scheduler, secrets, landsat_source, nwp_source
    pipeline/    m01_location m03_landsat m05_lst m06_heat m07_buildings m08_population
                 m085_context m09_priority m10_roofs m11_coolroof m14_actions
                 m15_heattype m16_drivers m24_trends m23_habitat m43_heatdome
    services/    m17_reco m18_advisory m20_readiness m22_fire m25_solar m26_roof m27_size
                 m29_subsidy m30_payback m32_suryacheck m35_pdf m37_alerts
    agent/       m33_agent (strands tools, system prompt, turn handler)
    api/         FastAPI app + routers (Mangum handler for Lambda)
  frontend/      React + Vite + MapLibre app (i18n en/hi), Playwright tests
  infra/         AWS CDK app (stacks: data, pipeline, api, frontend, alerts, monitoring)
  tests/         unit/ property/ golden/ (suryacheck, agent conversations) fixtures/ (mini city)
  data/          (gitignored) local BlobStore root
```

**Fixture "mini city"** for tests is a synthetic set:

- 12 wards
- ~500 footprints
- a population grid
- 3 small synthetic LST scenes
- an NDVI/BSI yearly series with known trends
- FIRMS sample CSV
- NWP sample JSON (ensemble) with a planted heat-dome event

Every module test must pass on it offline.

**Real demo city:** `config/cities/pune.yaml` by default [ASSUME]. The city is configurable; the ward layer source is [NV].

---

## 10. Missing-data rules (consolidated)

| Missing | Behaviour |
|---|---|
| Ward polygons | H3 / 500 m grid, `unit_type: grid` |
| Point outside wards / DISCOM ambiguous | 404 / ask the user |
| Few valid Landsat observations | `low_confidence`; no imputation |
| Any context field | `unavailable`; lower `context_confidence`; never 0 |
| Footprints sparse | `buildings_incomplete`; roof ranking withheld |
| Scoring variable | drop, renormalise, record `variables_used`; unscored if heat and population are both missing |
| Cool-roof coefficients / cost | scenario ranges; no BC ratio without `P-CM2` |
| Heat-type inputs | `undetermined` |
| Rule inputs | `not_evaluated` with missing fields |
| Driver support | `outside_model_support` |
| TTS provider / Hindi voice | text only; Hindi via Polly |
| Facility / load data | `unavailable`; advisory-only electricity |
| FIRMS down | backoff, alarm, stale banner, no invented alerts |
| Fire-service feed absent | staff incident logging only |
| Protected-area licence | OSM fallback or skip M23 |
| Tree-cover loss dataset | NDVI-drop fallback, labelled |
| Too few years / fully built ward | `insufficient_data` / `not_applicable` |
| Rainfall series | raw trend + caveat |
| **NWP forecast source down** | M43 `unavailable` with last-run age; official warnings still relayed |
| **No ensemble** | deterministic criteria, `low_confidence` |
| Official warning feed | manual planner entry with source URL; else "no official warning on record" |
| Solar API | cache → NASA POWER → `unavailable` |
| Consumption | area-limited size + ask for a bill |
| Subsidy record absent / stale | "unknown"; stale flag; hard limit blocks the PDF |
| Tariff / net metering | generation + subsidy only; `payback_unavailable_*` |
| Agent number not grounded | regenerate once → template |
| DISCOM checklist | generic template badged "confirm on portal" |
| No consent | no name or address in the PDF |
| SMS registration | SMS disabled; email + in-app continue |

---

## 11. Parameters (all in `config/params.default.yaml`, none asserted)

| ID | Meaning | Module | Status |
|---|---|---|---|
| P-STQA, P-MINOBS, P-MODIS-RHO | ST uncertainty cutoff, min observations, MODIS check | M3–5 | [ASSUME] |
| P-TAU | Hot-exposure threshold | M8 | [ASSUME] |
| P-W | Priority weights | M9 | equal baseline |
| P-THETA-HEAT | θ_hi / θ_mid / θ_lo | M15 | [ASSUME] |
| P-THETA-RULE-* | θ_prio, θ_roof, θ_sol, θ_exp, θ_bare | M17 | [ASSUME] |
| P-DALB, P-KCOOL, P-KIND, P-PHI | Cool-roof physics / protected share | M11–13 | missing / [ASSUME] |
| P-CM2, P-PREP | Coating cost ₹/m², prep factor | M11–13 | [NV] / [ASSUME] |
| P-U, P-KWMIN | Usable roof fraction, min kW | M26 | [ASSUME] |
| P-AKW, P-KWSTEP | m²/kW, capacity step | M27+28 | [ASSUME] |
| P-TILT, P-AZ, P-LOSS | Orientation, loss scenarios | M25 | [ASSUME] |
| P-DEG, P-LID | Degradation, first-year loss (0) | M27+28 | [ASSUME] |
| P-GCOST | Gross cost per kW range | M30+31 | [NV] |
| P-SELF, P-ESC, P-OM, P-INV | Self-use, escalation, O&M, inverter | M30+31 | [ASSUME] |
| P-STALE-POLICY, P-HARD-POLICY | Policy review / block (e.g. 30 / 90 days) | M29 | [ASSUME] |
| P-COVER | Facility radius | M20+21 | [ASSUME] |
| P-FIRE-POLL, P-FIRE-CONF, P-FIRE-RADIUS | FIRMS polling, confidence floor, radius | M22 | [ASSUME] |
| P-PA-BUFFER | Protected-area buffer | M23 | [ASSUME] |
| **P-VEG-DROP, P-HPI-W, P-HPI-THETA, P-LOSS-ALERT** | NDVI-drop loss proxy, HPI weights, class cut-offs, loss alert | M23 | [ASSUME] |
| P-TREND-MIN, P-BUILT-NA, **P-COVMIN** | Min years, built cut-off, min valid coverage | M24 | [ASSUME] |
| **P-HD-T, P-HD-Z, P-HD-DAYS, P-HD-BOX, P-HD-P1/P2/P3** | Tmax anomaly, Z500 σ-anomaly, consecutive days, region box, risk probabilities | M43 | [ASSUME], tune by hindcast |
| P-ALERT-RATE | Alert rate limits | M37 | [ASSUME] |

---

## 12. Build plan for the coding agent

Build in order. Every stage ends with `make test` green and a short entry in `docs/DEMO.md`.

| Stage | Build | Done when |
|---|---|---|
| **0 Scaffold** | Repo layout, `core` (envelope, enums, errors, params loader, grounding lib, i18n number formatter), all adapters with local implementations, FastAPI skeleton + `/health`, mini-city fixtures, CI (lint, type check, tests) | `make dev` serves `/health`; fixtures load |
| **1 Heat pipeline** | M1+2, M3+4 (Planetary Computer STAC locally), M5, M6, M7, M8, M8.5, M9, M10, M11–13, M14, tile builder (PMTiles) | Mini city: ranked wards with components + rank interval; roof list with ranges; CSV export; all Verify tests |
| **2 SuryaCheck** | M25, M26, M27+28, M29 (seeded F1/F3 policy), M30+31 (TEST-DISCOM synthetic tariff), M32, `/solar/assess` | Golden JSON for 3 locations; 3 kW → ₹78,000; payback fixture = 2.0 yr; statuses for missing tariff/consumption |
| **3 Agent + PDF + UI MVP** | M33+34 (6 MVP tools, grounding, en/hi), M35+36 (WeasyPrint + Devanagari self-test), M38 MVP screens 1–3 and 5–8 and 10, M39 routers, M41 anon sessions + API key | Demo: pick ward → rank → roof → solar → chat (hi) → PDF; Playwright happy path; 0 ungrounded numbers |
| **4 Heat intelligence** | M15 (+ briefs), M16, M17 (+ cooling_options), M18+19 (approval, Deepgram EN / Polly HI / stub), M20+21 (advisory mode), M37, Cognito wiring (AWS only) | Recommendations with evidence and not_evaluated; approved advisory with audio; readiness prompts; alerts in outbox |
| **5 Hazards + forecast** | M22 (FIRMS + incident workflow + R-FR-01), **M43** heat-dome forecaster + hindcast script, official-warning manual entry | Planted heat-dome in fixture detected with expected first_day; FIRMS sample → classified events; incident report → confirm → approved public alert |
| **6 Environment** | M24 trend job + degradation signal + transition alerts, M23 Habitat Pressure Index + PA alerts (+ optional GBIF) | Synthetic series → expected classes; HPI monotonic; wording denylist passes |
| **7 AWS deploy** | CDK stacks, Step Functions, EventBridge schedules, SNS, Amplify, Budgets, dashboards; switch `RUNTIME=aws` | Same golden tests pass against the deployed API; canary green |
| **8 Data-gated (optional)** | M20+21 forecast mode, M15 GMM on SageMaker, roof-type model, Aurora | Only if data, licences or keys are provided; else documented in GAPS.md |

**Credentials the human must provide** (the agent stubs these until then):

- AWS account (requester-pays enabled)
- Bedrock model access (or `ANTHROPIC_API_KEY` for local)
- Deepgram key
- AWS Polly access
- FIRMS MAP_KEY
- Real DISCOM tariff records (verified)
- City ward layer

### Demo script (Stage 3 → 6)

1. Select the city → ΔLST map with the disclaimer.
2. Ward ranking → open the top ward. Show the component breakdown, heat type + authority brief, drivers ("associated with") and recommendations with evidence, including locality cooling options.
3. Top roofs → cool-roof ranges with assumption IDs → action list CSV under a budget.
4. Homeowner: click a roof → SuryaCheck shows "3 kW, ₹78,000 subsidy (policy v…, date)" and a payback range or the "unavailable" reason.
5. Agent in Hindi explains and walks through the checklist → PDF.
6. Forecast panel: heat-dome "elevated" signal (fixture) → staff readiness prompts → planner approves a public advisory → EN/HI audio.
7. Fire: FIRMS vegetation fire near a protected area → PA alert; staff logs a structure fire → confirms → public alert.
8. Environment tab: degradation signal map; protected-area habitat-pressure classes.

**Declare in the demo:**

- Cool-roof coefficients and cost are placeholders (ranges).
- The tariff is synthetic unless verified.
- Forecast and environment outputs are indicators or signals, not official warnings or diagnoses.
- LST accuracy and cool-roof benefit are not validated.

---

## Appendix A — Sources

- A1 JBVNL PM Surya Ghar CFA sheet: https://jbvnl.co.in/SOLAR/CFA_structure for PM Suryaghar.pdf
- A2 Pune district portal: https://pune.gov.in/scheme/pm-surya-gharmuft-bijli-yojna/
- A3 Secondary reporting on payment timing (Outlook Business explainer) — confirm on the portal
- A4 USGS Landsat cloud access: https://www.usgs.gov/landsat-missions/landsat-commercial-cloud-data-access
- A5 AWS Open Data, USGS Landsat: https://registry.opendata.aws/usgs-landsat/
- A6 Deepgram TTS languages: https://developers.deepgram.com/docs/tts-models-languages-overview
- A7 Deepgram TTS changelog: https://developers.deepgram.com/changelog/text-to-speech-changelog

## Appendix B — Verify before relying on it (track in `docs/GAPS.md`)

1. Official PM Surya Ghar guidelines: eligibility, documents, vendor/DCR, fractional kW, timing (F5, F6).
2. ERC tariff and net-metering orders per supported DISCOM (F7).
3. Landsat C2 L2 guide: scale/offset, QA bits, uncertainty, India coverage. Planetary Computer STAC access terms.
4. Footprint and ward-boundary licences; WorldPop, WorldCover, SoilGrids, DEM terms.
5. PVGIS parameters, limits and India coverage; NASA POWER endpoint.
6. FIRMS fields, confidence scales, latency, key terms; WDPA and OSM (ODbL) handling.
7. Strands SDK (tools, providers, deployment); Bedrock model availability; Polly Hindi voice/engine in region; Deepgram output formats and limits.
8. Cool-roof literature ranges (ΔAlbedo, k_cool, k_indoor) and local coating cost schedule.
9. AIDMI extreme-heat resource page → evidence.json and cooling_options.json entries.
10. IMD heatwave definitions and an official warning feed or manual procedure.
11. **Open-Meteo / GFS-GEFS / ECMWF open data terms, variables (Tmax, Z500), ensemble availability; ERA5 climatology access (M43).**
12. **Hansen GFC access and licence; CHIRPS access; GBIF terms (M23, M24).**
13. **City fire-service incident data permissions (M22).**
14. India SMS sender registration; SNS DLQ setup.
15. WeasyPrint on Lambda (fonts, Devanagari).
16. API Gateway timeout limits for the agent route.
17. Data-protection obligations for PDF personal data (consent, retention) — legal review.
