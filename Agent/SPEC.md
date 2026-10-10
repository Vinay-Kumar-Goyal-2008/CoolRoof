# SPEC — Technical Specification

> **Version:** 1.0 — Derived from [CoolRoof_Build_Spec_v0.3.md](CoolRoof_Build_Spec_v0.3.md)
> **Date:** 2026-10-10

---

## 1. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Language (Backend)** | Python 3.11 | All pipelines, services, API, agent |
| **Language (Frontend)** | TypeScript | React app |
| **Geo Libraries** | rasterio/GDAL, pystac-client, odc-stac, GeoPandas, shapely 2, exactextract, DuckDB-spatial, h3 | All raster/vector/spatial ops |
| **Stats / ML** | numpy, xarray, scikit-learn, xgboost, shap, statsmodels, pymannkendall, pvlib | Analytics, trends, driver attribution, solar |
| **API Framework** | FastAPI (locally) + Mangum (Lambda) | pydantic v2 models → auto OpenAPI spec |
| **Agent Framework** | Strands Agents SDK | Bedrock on AWS; pluggable local provider (Anthropic API / mock) |
| **PDF Generation** | Jinja2 → HTML → WeasyPrint | Container with Noto Sans + Noto Sans Devanagari fonts |
| **Frontend** | React + Vite + MapLibre GL + pmtiles + React Query + i18next (en/hi) | Playwright for E2E tests |
| **Infrastructure as Code** | AWS CDK (Python) | All AWS stacks |
| **Local Infrastructure** | docker compose | api + frontend containers; optional MinIO (S3) + DynamoDB Local; file/SQLite default |
| **CI / Lint** | pytest, mypy, ruff, Playwright | CI gates on every commit |

---

## 2. System Architecture

### 2.1 High-Level Architecture (AWS Target)

```
EXTERNAL DATA                     BATCH PROCESSING (Step Functions)        STORAGE
─────────────                     ────────────────────────────────         ───────
Landsat C2 L2 (S3 req-pays) ──┐  L-STAC search                          S3 Buckets:
Copernicus DEM, ESA WorldCover┤  → L-LST window read + QA mask           raw/ curated/ tiles/ models/
Buildings (Open Buildings/    ┤  → L-FEAT zonal stats                    rules/ audio/ exports/
  Overture), WorldPop         ┤  → L-CTX Ward Context Builder
Ward boundaries, OSM POIs     ┤  Trend job (M24/M23, multi-year)        DynamoDB Tables:
PVGIS / NASA POWER (API)      ┤  Heavy raster → Fargate (optional)       ward_context, roof_context,
NASA FIRMS (API)              ┤                                           policy, config, session,
NWP forecast (Open-Meteo/GFS) ┘  SCHEDULED (EventBridge)                 cache, alerts, advisories,
                                  FIRMS poller (M22)                       subscriptions, forecasts,
                                  Heat-dome forecaster (M43, daily)        environment
                                  Policy freshness (M42)
                                  Staleness job (M8.5)

ANALYSIS (Lambda, deterministic):
  scoring · roof ranking · cool-roof model · rules engine ·
  solar · subsidy · payback · readiness · habitat pressure · degradation signal

ML (SageMaker Processing, optional):
  M15 clustering · M16 drivers · M20+21 forecast back-tests

API Gateway (REST) ─── Cognito (planner/admin, Phase 2)
  ├─ Amplify frontend (React + MapLibre + PMTiles)
  ├─ Strands Agent (Lambda) → Bedrock model → tools = deterministic APIs
  ├─ PDF Lambda (WeasyPrint container) → S3 presigned URL
  └─ TTS adapter Lambda (Deepgram EN / Polly HI)

Alerts: producers → M37 → SNS (email/SMS) + in-app banner
CloudWatch + AWS Budgets across all
```

### 2.2 Flow Classes

| Flow | Trigger | Modules |
|---|---|---|
| **Batch** (per city and season) | Manual / scheduled | Landsat → LST → features → Ward Context → scores → tiles |
| **Request-time** | User API call | Solar, subsidy, payback, agent, PDF, recommendations |
| **Scheduled** | EventBridge cron | FIRMS polling, daily heat-dome forecast, policy freshness, context staleness, yearly trend job |

### 2.3 Local-First Adapters

Every external dependency has a `local` and `aws` implementation, selected by `RUNTIME=local|aws` env var.

| Interface | `local` Implementation | `aws` Implementation |
|---|---|---|
| `BlobStore` | `./data/` folder (filesystem) | S3 |
| `DocStore` | SQLite (JSON columns, same PK/SK scheme as DynamoDB) | DynamoDB |
| `LLM` | Anthropic API if `ANTHROPIC_API_KEY` set, else deterministic mock (calls tools by keyword) | Bedrock via Strands |
| `TTS` | Deepgram/Polly if keys exist, else silent-WAV stub | Deepgram EN / Polly HI |
| `Notifier` | Writes to `./data/outbox/*.json` | SNS |
| `Scheduler` | APScheduler in the API process | EventBridge |
| `LandsatSource` | Microsoft Planetary Computer STAC (`landsat-c2-l2`, free signed URLs), or cached fixture COGs | `s3://usgs-landsat` requester-pays (us-west-2) |
| `NWPSource` | Cached fixture JSON or Open-Meteo free API | Open-Meteo / GFS on AWS Open Data |
| `Secrets` | `.env` file | Secrets Manager |

### 2.4 AWS Services

**MVP (Phase 1):**
- S3 + Open Data
- Lambda (containers for geo and PDF)
- Step Functions
- DynamoDB
- API Gateway (REST)
- Amplify
- Bedrock + Strands Agents SDK
- CloudWatch
- Secrets Manager
- AWS Budgets

**Phase 2:**
- EventBridge Scheduler (FIRMS, M43 daily, freshness, staleness)
- SNS (alerts)
- Cognito
- Amazon Polly (Hindi TTS)

**Optional / Scale:**
- SageMaker Processing (M15 clustering, M16 drivers, M20+21 back-tests)
- Fargate (large rasters, trend job)
- Aurora PostGIS (only if DuckDB is outgrown)
- SQS (DLQ / buffer)
- Amazon Location (routing)
- WAF

**Explicitly NOT used:** Kubernetes/EKS, Glue, EMR, Kinesis, Redshift, OpenSearch.

**Region:** Landsat processing runs in **us-west-2** (next to the bucket). Only small curated outputs are copied to the user-facing region.

---

## 3. Database Schema

### 3.1 DynamoDB Tables

| Table | PK | SK | GSI | Notes |
|---|---|---|---|---|
| **ward_context** | `city#<ward_id>` | `ctx#<version>` | `city + priority_rank` | Ward Context (§4.2 of spec). Also stores recommendations at SK `reco#<ctx>#<rules>` |
| **roof_context** | `ward#<building_id>` | `ctx#<version>` | — | Per-building context |
| **policy** | `policy#<type>#<state>#<discom>` | `<effective_date>` | — | Types: `subsidy`, `subsidy_topup`, `tariff`, `netmetering`, `checklist`, `imd_heatwave_criteria`. National records use state=`ALL`, discom=`ALL` |
| **config** | `config#<city\|global>` | `<type>#<version>` | — | All P-* parameter values, rules pointer, `electricity_mode`, author + date |
| **session** | `session#<id>` | — | — | TTL-based; 128-bit random id; agent conversation state |
| **cache** | `solar#<cell>` or `tts#<hash>` | — | — | TTL-based; solar resource cache by 0.1° cell; TTS audio cache by content hash |
| **alerts** | `fire#<city>` or `ward#<id>` | `<ts>#<id>` | GSI: `status`, `ward_id` | Fire events, fire incidents, audit trail |
| **advisories** | `ward#<id>` | `adv#<id>` | GSI: `status` | Advisory records with approval workflow |
| **subscriptions** | `ward#<id>` | `sub#<id>` | GSI: `status` | Email/SMS subscriptions (addresses stored hashed) |
| **forecasts** | `city#<slug>` | `<issued_at>` | — | M43 heat-dome forecast records |
| **environment** | `pa#<id>` or `ward#<id>` | `<year>#<indicator>` | — | M23 HPI summaries, M24 trend series summaries (detail in S3) |

**Key design decisions:**
- On-demand capacity mode
- PITR (Point-in-Time Recovery) enabled on durable tables
- Items ≤ 400 KB; larger detail goes to S3 with a DynamoDB pointer
- Encryption at rest
- No PII outside sessions, hashed subscriptions, and PDFs

### 3.2 S3 Bucket Layout

```
s3://<bucket>/
  raw/                          # Raw raster downloads (Landsat scenes, DEM, WorldCover)
  curated/                      # Processed feature tables, parquet files
    _registry/                  # Dataset registry (name, version, url, licence, sha256, bbox, resolution)
    climatology/<city>.parquet   # M43 climatology cache
    soil/series.parquet          # M24 per-ward yearly series
  tiles/                        # PMTiles for map layers (ΔLST, LST raster)
  models/                       # ML model artefacts (M15 GMM, M16 GBM)
  rules/v<N>/                   # Immutable versioned rule sets
    rules.json
    evidence.json
    cooling_options.json
    heat_type_briefs.json
    advice.json
    templates/{en,hi}/*.j2
    glossary.json
  audio/                        # TTS audio files (keyed by content hash)
  exports/                      # Generated PDFs, CSV exports
```

### 3.3 Ward Context Schema

The central data contract. Every field is wrapped in a **Value Envelope**:

```json
{
  "value": 3.8,
  "class": "derived",
  "source": "landsat_c2l2_st; season=2026-MarJun; years=3",
  "observed": "2024-03..2026-06",
  "processed": "2026-10-07",
  "resolution_m": 30,
  "confidence": 0.7,
  "stale_after": "2027-07-01"
}
```

**Value classes:** `measured | derived | estimated | policy | user | unavailable | stale`

**Schema sections:**

```
ward_id, boundary_version, context_version
location:          city, state, centroid, area_km2, unit_type(ward|grid)
heat:              mean_dlst_c, p90_lst_c, persistence, z_vs_city, n_obs, heat_type,
                   top_drivers, drivers_ref,
                   heatdome_risk, heatdome_ref                          # M43
built_environment: building_count, roof_area_m2, built_fraction, eligible_roof_area_m2
population:        population, density, exposed_population
environment:       ndvi_mean, water_distance_m, elevation_mean_m,
                   ndvi_trend_slope, bsi_trend_slope, lst_trend_slope,   # M24
                   degradation_signal, bare_fraction, soc_mean
infrastructure:    hospital_count, school_count, cooling_point_count,
                   nearest_hospital_m, facilities_per_10k_exposed
solar:             specific_yield, rooftop_potential_kwp_est
hazards:           fire_events_30d, fire_incidents_30d,                  # M22
                   protected_area_overlap, nearest_protected_area_m,
                   habitat_pressure_max                                  # M23
administrative:    discom, policy_ref
data_quality:      available, unavailable, estimated, stale, context_confidence (0..1)
```

**Write rules:**
- Only **M8.5** writes whole context versions.
- **M22, M23, M43** may make path-limited conditional updates to `hazards.*` and `heat.heatdome_*` on the latest version (these change faster than batch).
- Other modules write feature tables to `curated/`, and M8.5 reads them on its next build.

### 3.4 Roof Context Schema

```
building_id (= roof_id = hash(dataset_id + geometry))
geometry, area, local_heat, pop_b, floors_est?,
solar: {yield, kWp_max}
intervention: {cost, benefit}
policy_ref, ward_ref
```

### 3.5 Key Identifiers and Enums

**Identifiers:**
- `city` (slug), `ward_id`, `boundary_version`, `context_version` (date-stamped)
- `building_id = roof_id = hash(dataset_id + geometry)`
- `run_id` (batch execution)
- `rules_version`, `templates_version` (immutable S3 prefixes)
- `policy key = policy#<type>#<state>#<discom>` with SK `effective_date`
- `session_id` (128-bit random)
- `alert_id`, `advisory_id`, `forecast_id` (uuid)
- `dedupe_key = sha1(round(lat,4), round(lon,4), date, time, instrument)` (fire)
- `engine_version`, `input_hash`

**Core Enums:**

| Enum | Values |
|---|---|
| SolarAssessment field class | `FACT \| ASSUMPTION \| USER \| ESTIMATE` |
| Payback status | `ok \| payback_range_cost_assumed \| payback_unavailable_no_tariff \| payback_unavailable_stale_tariff \| payback_unavailable_unsupported_discom \| payback_unavailable_no_consumption` |
| Eligibility | `unconfirmed \| likely \| not_eligible_per_answers` |
| Heat type | `undetermined \| not_hot \| episodic \| dense_built_low_green \| open_bare_or_industrial \| chronic_other` |
| Suitability | `suitable \| check_obstructions \| unsuitable \| unknown` |
| Fire class (satellite) | `vegetation_fire (forest_fire) \| agricultural_burning_candidate \| urban_thermal_anomaly_candidate \| unclassified \| persistent_source` |
| Fire class (incident) | `structure_fire_reported \| structure_fire_confirmed` |
| Trend class | `declining \| stable \| increasing \| insufficient_data \| not_applicable` |
| Degradation signal | `none \| weak \| moderate \| strong \| insufficient_data \| not_applicable` |
| Habitat pressure | `low \| moderate \| high \| insufficient_data` |
| Heat-dome risk | `none \| watch \| elevated \| high \| unavailable` |
| Alert/advisory status | `draft \| approved \| auto_info \| published \| sent \| suppressed \| expired \| withdrawn` |
| Electricity mode | `advisory \| forecast` |
| Unit type | `ward \| grid` |

---

## 4. API Endpoints (v1)

### 4.1 Response Envelope

**Success:**
```json
{
  "data": { ... },
  "meta": {
    "request_id": "...",
    "context_version": "...",
    "policy_version": "...",
    "warnings": []
  }
}
```

**Error:**
```json
{
  "error": {
    "code": 404,
    "message": "Ward not found"
  }
}
```

**Error Codes:**
- `400` — validation
- `401/403` — auth
- `404` — outside coverage
- `409` — run in progress / already approved
- `422` — incomplete or withheld
- `424` — policy missing or stale (when policy is required)
- `429` — throttled
- `502` — upstream failed with nothing to return
- `504` — timeout (idempotent retry)

### 4.2 Endpoint Table

| Endpoint | Method | Module | Key Response | Errors |
|---|---|---|---|---|
| `/locations/resolve` | GET/POST | M1+2 | LocationRef | 404 |
| `/analysis/heat` | POST | pipeline | execution id (202) | 409, 403 |
| `/analysis/heat/{id}` | GET | pipeline | execution state | 409 |
| `/wards` | GET | M9 | wards with components, rank interval (`?city=&sort=priority`) | 404 |
| `/wards/{id}/context` | GET | M8.5 | ward_context | 404 |
| `/wards/{id}/buildings` | GET | M10 | ranked roofs with ranges (`?top=&budget=`) | 422 |
| `/buildings/{id}/context` | GET | M8.5 | roof_context | 404 |
| `/interventions/plan` | POST | M14 | plan + CSV link | 422 |
| `/wards/{id}/heat-type` | GET | M15 | type, confidence, evidence, authority brief | 404 |
| `/wards/{id}/drivers` | GET | M16 | drivers[], unobserved[], model card | 404, 422 |
| `/wards/{id}/recommendations` | GET | M17 | recommendations[], not_evaluated[] (`?objective=`) | 404 |
| `/cooling-options` | GET | M17 | matched catalog entries with evidence (`?ward=`) | 404 |
| `/advisories` | POST | M18+19 | draft advisory | 403, 422 |
| `/advisories/{id}/approve` | POST | M18+19 | approved advisory | 403, 409 |
| `/tts` | POST | M18+19 | audio_url | 502 |
| `/wards/{id}/readiness` | GET | M20+21 | facilities, distances, prompts[] | 404 |
| `/fire/events` | GET | M22 | satellite fire events (`?bbox=&since=`) | 400 |
| `/fire/incidents` | POST | M22 | incident record | 403, 422 |
| `/fire/incidents/{id}/confirm` | POST | M22 | confirmed incident | 403, 422 |
| `/fire/incidents` | GET | M22 | incident list (`?city=`) | — |
| `/protected-areas` | GET | M23 | protected areas (`?city=`) | 404 |
| `/protected-areas/{id}/pressure` | GET | M23 | HPI, indicators | 404 |
| `/protected-areas/alerts` | GET | M23 | PA alerts (`?city=`) | 404 |
| `/wards/{id}/soil` | GET | M24 | series summary, trends, degradation_signal (status: indicator) | 404 |
| `/forecast/heatdome` | GET | M43 | latest forecast + official warning ref (`?city=`) | 404 |
| `/forecast/heatdome/history` | GET | M43 | forecast history (`?city=`) | 404 |
| `/solar/assess` | POST | M32 | SolarAssessment (complete/partial) | 424, 502 |
| `/policy/subsidy` | GET | M29 | policy record (`?state=&discom=&date=`) | 404 |
| `/checklist` | GET | M35+36 | checklist items (`?state=&discom=&applicant=`) | 404 |
| `/documents/application-pdf` | POST | M35+36 | presigned url + expires_at | 422, 424 |
| `/sessions` | POST | M41 | session_id | 429 |
| `/agent/chat` | POST | M33+34 | reply, citations[], trace_id | 429, 504 |
| `/alerts` | GET | M37 | active alerts (`?ward=`) | — |
| `/alerts/subscriptions` | POST/DELETE | M37 | subscription record | 422, 429 |
| `/admin/policy` | PUT | M41 | version | 403, 422 |
| `/admin/config` | PUT | M41 | version | 403, 422 |
| `/admin/official-warnings` | POST | M41 | warning record | 403, 422 |
| `/health` | GET | M42 | status, versions | — |

### 4.3 API Routers (one per domain)

```
api/
  routers/
    locations.py        # /locations/*
    analysis.py         # /analysis/*
    wards.py            # /wards/*
    solar.py            # /solar/*
    agent.py            # /agent/*
    documents.py        # /documents/*
    alerts.py           # /alerts/*
    fire.py             # /fire/*
    environment.py      # /protected-areas/*, /wards/{id}/soil
    forecast.py         # /forecast/*
    admin.py            # /admin/*
    health.py           # /health
```

---

## 5. Component Structure

### 5.1 Repository Layout

```
coolroof/
  README.md
  Makefile
  docker-compose.yml
  .env.example
  pyproject.toml

  docs/
    SPEC.md              # This file (the build spec)
    GAPS.md              # Unverified items tracker
    DEMO.md              # Demo walkthrough notes
    DATA_SOURCES.md      # Data source documentation

  config/
    params.default.yaml  # Every P-* parameter (value|null, status, source)
    cities/<city>.yaml   # bbox, season, UTM EPSG, DISCOM map, weight profile

  rules/v1/
    rules.json
    evidence.json
    cooling_options.json
    heat_type_briefs.json
    advice.json
    templates/{en,hi}/*.j2
    glossary.json

  seed/
    policy/
      subsidy_pm_surya_ghar.json       # F1/F3 [V]
      tariff_TEST-DISCOM.json          # SYNTHETIC, test-only
      checklist_generic.json           # All items = needs_official_check
      imd_heatwave_criteria.json       # [R], needs_verification

  packages/
    core/                # Shared foundations
      envelope.py        # Value envelope class
      ids.py             # ID generation (building, session, alert, etc.)
      enums.py           # All enum definitions
      errors.py          # Error hierarchy
      params.py          # Parameter registry + loader
      provenance.py      # Provenance tracking
      grounding.py       # Number grounding library
      i18n.py            # Indian number formatting (en/hi)

    adapters/            # Interface + local/aws implementations
      blobstore.py       # BlobStore interface
      docstore.py        # DocStore interface
      llm.py             # LLM interface
      tts.py             # TTS interface
      notifier.py        # Notifier interface
      scheduler.py       # Scheduler interface
      secrets.py         # Secrets interface
      landsat_source.py  # Landsat source interface
      nwp_source.py      # NWP forecast source interface

    pipeline/            # Batch processing modules
      m01_location.py
      m03_landsat.py
      m05_lst.py
      m06_heat.py
      m07_buildings.py
      m08_population.py
      m085_context.py    # Ward Context Builder
      m09_priority.py
      m10_roofs.py
      m11_coolroof.py
      m14_actions.py
      m15_heattype.py
      m16_drivers.py
      m24_trends.py
      m23_habitat.py
      m43_heatdome.py

    services/            # Request-time and scheduled services
      m17_reco.py
      m18_advisory.py
      m20_readiness.py
      m22_fire.py
      m25_solar.py
      m26_roof.py
      m27_size.py
      m29_subsidy.py
      m30_payback.py
      m32_suryacheck.py
      m35_pdf.py
      m37_alerts.py

    agent/               # AI agent
      m33_agent.py       # Strands tools, system prompt, turn handler

    api/                 # FastAPI application
      app.py             # FastAPI app init + Mangum handler
      routers/           # One router per domain (see §4.3)

  frontend/              # React + Vite + MapLibre
    src/
      components/        # UI components
      pages/             # Route pages (11 screens per §5 M38)
      hooks/             # React hooks
      i18n/              # en.json, hi.json translations
      lib/               # API client, map utils
    playwright/          # E2E tests

  infra/                 # AWS CDK (Python)
    stacks/
      data.py            # S3, DynamoDB
      pipeline.py        # Step Functions, Lambda
      api.py             # API Gateway, Lambda
      frontend.py        # Amplify
      alerts.py          # SNS, EventBridge
      monitoring.py      # CloudWatch, Budgets

  tests/
    unit/                # Per-module unit tests
    property/            # Property-based tests (hypothesis)
    golden/              # Golden fixture tests
      suryacheck/        # 3-location golden JSON
      agent/             # 30-turn conversation suite
    fixtures/            # Mini city fixture data
      mini_city/
        wards.geojson          # 12 synthetic wards
        buildings.parquet      # ~500 footprints
        population.tif         # Population grid
        lst_scenes/            # 3 small synthetic LST scenes
        ndvi_bsi_series/       # Yearly NDVI/BSI with known trends
        firms_sample.csv       # FIRMS fire data
        nwp_ensemble.json      # NWP sample with planted heat-dome

  data/                  # (gitignored) Local BlobStore root
```

### 5.2 Frontend Screens (M38)

| # | Screen | Description |
|---|---|---|
| 1 | City / ward picker | Select city, browse ward boundaries on map |
| 2 | Heat map | ΔLST/LST raster (PMTiles) with LST disclaimer |
| 3 | Ward ranking | Component bars, rank interval, confidence |
| 4 | Ward panel | Context, heat type + authority brief, drivers, recommendations, readiness, degradation |
| 5 | Roof list | Ranked buildings in a ward |
| 6 | Roof detail | Cool-roof impact ranges |
| 7 | SuryaCheck card | Solar assessment UI |
| 8 | Agent chat | EN/हिंदी bilingual chat |
| 9 | Alerts and forecast | Heat-dome forecast banner + panel, fire events, PA alerts |
| 10 | PDF download | Generate and download assessment PDF |
| 11 | Planner console | Approve advisories, log fire incidents |

**Provenance UI:** Every number has a class badge. Source, date, and resolution on hover. Withheld or unavailable states show the reason, never a blank.

### 5.3 Agent Tools (M33+34)

**MVP tools:**
- `get_ward_context` — Retrieve ward context data
- `get_solar_assessment` — Run SuryaCheck pipeline
- `get_subsidy_rules` — Query subsidy policy
- `get_checklist` — State/DISCOM-specific checklist
- `generate_application_pdf` — Generate bilingual PDF
- `request_user_input` — Prompt user for information

**Phase 2 tools:**
- `get_roof_context` — Retrieve roof context
- `get_heat_analysis` — Heat type + drivers
- `get_recommendations` — Ward recommendations
- `get_readiness` — Hospital/electricity readiness
- `get_alerts` — Active alerts
- `get_advisory` — Advisory records
- `get_heatdome_forecast` — Heat-dome forecast
- `get_habitat_pressure` — Protected area HPI
- `get_degradation` — Land degradation indicators

**Not in the agent's registry:** Admin and planner write tools (policy edit, config edit, advisory approval, fire incident logging).

---

## 6. ML Models Summary

| Model | Status | Baseline | Method | Evaluation |
|---|---|---|---|---|
| LST (M5) | No ML | USGS L2 product | — | MODIS cross-check |
| Heat-type clustering (M15) | Optional 2nd opinion | Rule archetypes | GMM (k=2..6, BIC) | Bootstrap ARI, expert review |
| Driver attribution (M16) | Phase 2 | OLS | GBM + SHAP | Spatial-CV R², Moran's I |
| Heat-dome forecast (M43) | Phase 2 | Deterministic criteria | Ensemble exceedance probability | Hindcast hit rate, FAR, Brier score |
| Habitat pressure / degradation (M23/M24) | Phase 3 | Indicator thresholds | Mann–Kendall + Sen's trends, percentile index | Synthetic series, visual checks |
| Electricity demand (M20+21) | Phase 3, data-gated | Seasonal naive | Regression on air temp | Rolling MAPE |
| Roof type | Phase 3, optional | User confirmation | CNN | IoU |
| Agent (M33+34) | Yes | Template UI | Bedrock via Strands | Golden suite, 100% grounding |

---

## 7. Auth Model

| Capability | Anon | Viewer | Planner | Admin |
|---|---|---|---|---|
| SuryaCheck, agent, PDF | ✓ | ✓ | ✓ | ✓ |
| Read ward ranking, context, recommendations, forecasts | ✓ [ASSUME] | ✓ | ✓ | ✓ |
| Run analysis, action plan | | | ✓ | ✓ |
| Create/approve advisories and alerts; log/confirm fire incidents | | | ✓ | ✓ |
| Edit weights, thresholds, rules pointer | | | | ✓ |
| Edit policy records (verified_by required) | | | | ✓ (MFA) |

- Anonymous sessions use 128-bit random id with TTL
- Cognito is Phase 2; demo uses API key on planner routes
- Roles can be scoped to a city
- All writes are immutable versions with author and timestamp

---

## 8. Key Algorithms and Formulas

### 8.1 Ward Priority Score (M9)

```
Normalisation: within-city percentile pct(·) ∈ [0,1]

Components:
  H = pct(ΔLST_mean)               # heat intensity
  P = pct(persistence)             # chronic heat
  E = pct(exposed_pop)             # people exposed
  V = 1 − pct(NDVI)               # lack of green
  R = pct(eligible roof area / ward area)  # roof opportunity
  F ∈ [0,1]                        # feasibility gate

Formula:
  Need = (a_H·H + a_P·P + a_E·E + a_V·V) / Σa
  Priority = Need · (0.5 + 0.5·R) · F

Sensitivity: Dirichlet (1000 draws) → rank interval + top-10 stability
```

### 8.2 PM Surya Ghar Subsidy (M29)

```
Residential:
  S(c) = 30000·min(c,2) + 18000·max(0, min(c,3) − 2)
  → 1 kW = ₹30,000 | 2 kW = ₹60,000 | 3 kW = ₹78,000 | 5 kW = ₹78,000

GHS/RWA:
  S = 18000·c  (common facilities incl. EV, ≤500 kW at 3 kW/house)
```

### 8.3 Heat-Dome Forecast (M43)

```
for member m, day d (1..H):
  T_anom = Tmax[m,d] − clim_mean_T(doy)
  hotT = Tmax[m,d] ≥ clim_p90_T(doy) and T_anom ≥ P-HD-T
  Z_anom = mean_box(Z500[m,d]) − clim_mean_Z(doy)
  ridge = Z_anom ≥ P-HD-Z · clim_std_Z(doy)
  signal[m,d] = hotT and ridge

event[m] = any run of ≥ P-HD-DAYS consecutive signal days
p_event = share of members with event
risk = none | watch (p ≥ P-HD-P1) | elevated (p ≥ P-HD-P2) | high (p ≥ P-HD-P3)
```

### 8.4 Land Degradation Signal (M24)

```
Count adverse significant trends among:
  - NDVI ↓ (rain-adjusted if possible)
  - BSI ↑
  - LST ↑

0 → none | 1 → weak | 2 → moderate | 3 → strong
Fully built wards (> P-BUILT-NA) → not_applicable
```

### 8.5 Habitat Pressure Index (M23)

```
HPI = Σ w_i · pct_i

Indicators:
  I_fire  — vegetation fire count/area vs multi-year mean
  I_loss  — tree-cover loss % (Hansen or NDVI-drop fallback)
  I_veg   — NDVI trend slope (Mann–Kendall)
  I_heat  — LST trend slope

Classes: low | moderate | high  (from P-HPI-THETA)
```

---

## 9. Monitoring and CI Gates (M42)

### 9.1 Metrics and Alarms

| Category | Metrics |
|---|---|
| Batch | Scenes processed, valid %, low-confidence wards, bytes read |
| API | 5xx rate, p95 latency |
| Agent | Grounding pass rate, fallback rate, tokens |
| Policy | Age since last update |
| FIRMS | Poll success, latency, DLQ depth |
| Solar | Fallback share (PVGIS vs POWER vs cache) |
| M43 | Forecast run success, source age |
| M24/M23 | Trend job coverage |
| Cost | AWS Budgets |

### 9.2 CI Gates

- Unit and property tests
- SuryaCheck golden fixtures
- Golden agent suite (zero ungrounded numbers)
- Heat-pipeline regression on fixture city (rank ρ ≥ floor)
- Schema validation
- Wording denylist tests

### 9.3 Scheduled Jobs

- Policy-freshness check
- Synthetic canary on `/solar/assess`
- Context staleness flip
