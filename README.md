# CoolRoof — Urban Heat Prioritisation + Rooftop Solar (SuryaCheck)

> **Which roofs should a city cool first — and can your home go solar?**

CoolRoof is a full-stack urban-heat intelligence platform that ranks city wards and rooftops for cool-roof action using Landsat surface temperature data, and gives households a locality-aware rooftop-solar check (PM Surya Ghar subsidy, payback range, Hindi/English assistant, PDF summary).

**Built for AWS Hackathon 2026 · Team: Deepanshu Nain, Vinay Kumar Goyal, Vaatsalya Srivastava , Sumit Singh**

[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python_3.12-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![AWS CDK](https://img.shields.io/badge/AWS_CDK-Python-FF9900?logo=amazonaws)](https://aws.amazon.com/cdk/)
[![MapLibre](https://img.shields.io/badge/MapLibre-GL-396CB2?logo=maplibre)](https://maplibre.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Table of Contents

- [Delhi MCD Data Layer](#-delhi-mcd-data-layer-deepanshu-branch)
- [Repository Layout](#-repository-layout)
- [Quick Start](#-quick-start)
- [Environment Configuration](#-environment-configuration)
- [API Usage Examples](#-api-usage-examples)
- [Running Tests](#-running-tests)
- [Deploy to AWS](#-deploy-to-aws)
- [Architecture](#-architecture)
- [License](#-license)

## 🗺 Delhi MCD Data Layer

| Data | Details |
|---|---|
| **12 MCD Administrative Zones** | Real GeoJSON boundaries (Rohini, Civil Lines, City-SP/Chandni Chowk, Karol Bagh, South Delhi, West Delhi, Shahdara, East Delhi, North-East, Dwarka, Narela, New Delhi) |
| **Heat type classification** | Rank-based: `dense_asphalt_canyon` / `industrial_bare_metal` / `mixed_vegetated` with confidence 0.92 |
| **Ward heat summary** | ΔLST, population, exposed population, priority rank (1–12), rank interval, degradation signal |
| **Recommendations** | 3 tiered interventions per zone: cool roof coating (T1), shade + misting (T2), urban greening (T3) with evidence grades and pricing |
| **Top roofs to cool** | 3 ranked rooftop buildings per zone with area, protected-people range, benefit, cost-INR, neighbourhood ΔT |
| **Heat drivers** | 4 XGBoost/SHAP-style drivers: impervious cover (+3.4 °C), canopy deficit (+2.1 °C), dark rooftops (+1.6 °C), traffic heat (+0.8 °C) |
| **Readiness** | Hospital/school/cooling-point counts, nearest hospital, emergency prompts for HOSP/COOL audiences |
| **Soil/land** | NDVI + BSI + LST trend series (2021–2024), urban soil baseline |
| **Hotspots** | Urban thermal anomaly candidates (GeoJSON points) |
| **Facilities** | Hospitals, schools, cooling centres (GeoJSON) |
| **Forecast signal** | IMD-style orange heatwave alert for Delhi NCT |

## 📁 Repository Layout

```
CoolRoof/
├── backend/          # Python 3.12 (uv). FastAPI + pipeline + agent + adapters
│   ├── packages/
│   │   ├── core/     # Envelope, params, grounding, i18n, wording rules
│   │   ├── adapters/ # local / AWS implementations (S3, DynamoDB, SNS, Polly…)
│   │   ├── pipeline/ # Landsat, LST, ΔLST, hotspots, footprints, scoring, roofs
│   │   ├── services/ # Recommendations, advisories, fire, solar, PDF, alerts
│   │   └── agent/    # Strands agent, 17 tools, system prompt
│   ├── api/          # FastAPI routers (every route in spec §6)
│   ├── config/       # params.default.yaml, cities/
│   ├── rules/v1/     # Heat-type rules, evidence registry, cooling options
│   ├── seed/         # Policy, tariff, checklist seed data
│   └── tests/        # unit, property, golden, e2e (12-ward mini_city fixture)
├── frontend/         # Next.js 15 + MapLibre, EN/हिंदी
│   ├── app/          # /app shell (Overview, Heat map, Solar, Assistant, Alerts, Planner)
│   ├── components/   # WardMap, WardPanel, SolarCard, Shell, ChatPanel…
│   ├── lib/          # api.ts, data.tsx, delhi_data.ts, i18n.ts
│   └── e2e/          # Playwright tests
├── infra/            # AWS CDK (Python) — 6 stacks: Data, Alerts, Auth, Api, Jobs, Monitoring
├── docs/             # GAPS.md, DEMO.md, DATA_SOURCES.md
├── Agent/            # Original specs (CoolRoof_Build_Spec_v0.3.md, TASKS.md, PRD)
└── docker-compose.yml
```

## 🚀 Quick Start

**Requirements:** `uv`, Node 18+, Windows (no GDAL/GTK/make needed).

### 1. Clone the repository

```powershell
git clone https://github.com/Vinay-Kumar-Goyal-2008/CoolRoof.git
cd CoolRoof
git checkout Deepanshu
```

### 2. Backend setup

```powershell
cd backend
uv sync --all-extras
uv run poe pipeline-mini     # Run heat pipeline on synthetic Pune city → backend/data/
uv run poe api               # Start API at http://localhost:8000/docs
```

### 3. Frontend setup

```powershell
cd ..\frontend
npm install
npm run dev                  # http://localhost:3000
```

> The frontend proxies `/api/*` to `:8000`. For **Delhi mode**, no backend is required — all data is served offline.

### 4. Environment file

```powershell
cp backend\.env.example backend\.env
```

---

## ⚙️ Environment Configuration

Edit `backend/.env`. Key variables:

```dotenv
# Runtime: "local" (default) or "aws"
RUNTIME=local

# Required for planner console (dev defaults work locally)
PLANNER_API_KEY=dev-planner-key
ADMIN_API_KEY=dev-admin-key

# Optional: real LLM. If empty, deterministic mock agent is used.
ANTHROPIC_API_KEY=

# Optional: text-to-speech. If empty, silent-WAV stub is used.
DEEPGRAM_API_KEY=

# Optional: live FIRMS fire data. If empty, fixture is used.
FIRMS_MAP_KEY=
```

Model and scoring assumptions live in `config/params.default.yaml`. Each parameter has an ID (e.g. `P-TAU`), a value and a status: `[ASSUME]`, `[NV]` (needs verification) or `[V]` (verified). City settings live in `config/cities/<city>.yaml`.

## 🔌 API Usage Examples

All responses use the envelope `{ "data": ..., "meta": { "request_id", "context_version", "warnings" } }`. Errors return `{ "error": { "code", "message" } }`.

### Rank wards by cool-roof priority

```bash
curl "http://localhost:8000/wards?city=mini_city&sort=priority"
```

### Get a ward's heat type, drivers and recommendations

```bash
curl "http://localhost:8000/wards/<ward_id>/heat-type"
curl "http://localhost:8000/wards/<ward_id>/drivers"
curl "http://localhost:8000/wards/<ward_id>/recommendations?lang=en"
```

### List top roofs to cool

```bash
curl "http://localhost:8000/wards/<ward_id>/buildings?top=8"
```

### Check the heat-dome forecast signal

```bash
curl "http://localhost:8000/forecast/heatdome?city=mini_city"
```

### Run a solar assessment (SuryaCheck)

```bash
curl -X POST http://localhost:8000/solar/assess \
  -H "Content-Type: application/json" \
  -d '{"lat": 28.6139, "lon": 77.2090, "state": "Delhi", "discom": "BSES Rajdhani"}'
```

> See `/docs` for the full `SolarRequest` schema including optional `roof_area_m2`, `avg_monthly_kwh`, `gross_cost_inr`.

### Chat with the agent (English or Hindi)

```bash
# Create an anonymous session
curl -X POST http://localhost:8000/sessions

# Ask a question in English
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<session_id>", "message": "Which ward needs cool roofs most urgently?", "lang": "en"}'
```

### Key endpoint reference

| Area | Endpoints |
|---|---|
| **Locations** | `GET/POST /locations/resolve` |
| **Heat analysis** | `POST /analysis/heat`, `GET /wards`, `GET /wards/{id}/context` |
| **Roofs and plans** | `GET /wards/{id}/buildings`, `POST /interventions/plan` |
| **Heat intelligence** | `/wards/{id}/heat-type`, `/drivers`, `/recommendations`, `/readiness` |
| **Advisories** | `POST /advisories`, `POST /advisories/{id}/approve`, `POST /tts` |
| **Hazards** | `/fire/events`, `/fire/incidents`, `/protected-areas`, `/wards/{id}/soil` |
| **Forecast** | `/forecast/heatdome`, `/forecast/heatdome/history` |
| **Solar** | `POST /solar/assess`, `GET /policy/subsidy`, `GET /checklist` |
| **Agent and alerts** | `POST /agent/chat`, `GET /alerts`, `POST /alerts/subscriptions` |

## 🧪 Running Tests

Every module ships with tests. All run offline on the synthetic mini_city fixture (12 wards, ~500 footprints, sample scenes, FIRMS and forecast data).

```powershell
cd backend
uv run poe test          # Full suite (~6 min)
uv run poe lint          # ruff + mypy (both clean)
uv run poe typecheck

# Specific suites
uv run pytest tests/unit
uv run pytest tests/property
uv run pytest tests/golden

# Frontend E2E (needs API on :8000 and app on :3000)
cd ..\frontend
npm run test:e2e
```

Notable checks:
- **SuryaCheck golden tests:** 70 m² roof, 400 units/month, ₹1,80,000 quote → 3 kW, ₹78,000 subsidy, payback range
- **Grounding:** every number the agent states must come from a tool output
- **Wording denylist:** tests fail if outputs call LST "air temperature", call forecasts "official warnings", or use "loss" / "diagnosis" for indicators

CDK offline tests:
```powershell
cd ..\infra
pytest    # 7 offline tests that synthesise every CDK stack and check wiring
```

---

## ☁️ Deploy to AWS

Full steps: **`infra/README.md`**. Short version:

```powershell
cd infra
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
npm install
npx cdk bootstrap
npx cdk deploy --all -c bedrock_model_id=<id> -c ops_email=you@example.com
```

Then load data:

```powershell
cd ..\backend
$env:RUNTIME="aws"
$env:S3_BUCKET="<bucket from stack output>"
uv run python -m scripts.run_pipeline --city mini_city
```

Set `BACKEND_URL=<ApiUrl>` for the frontend (`next.config.mjs` proxies `/api/*` to it).

> ⚠️ **Never deployed yet.** The `S3BlobStore`, `DynamoDocStore`, `SNSNotifier`, `SecretsManagerSecrets`, `PollyTTS` and Cognito paths have never run against real AWS. Fix what the first real deploy exposes.


## 🏛 Architecture

```mermaid
flowchart TB
    B["Browser — Next.js 15"]

    subgraph FRONTEND["Frontend"]
        direction TB

        subgraph HEAT["/app/heat"]
            WM["WardMap — MapLibre"]
            WP["WardPanel"]
            DEL{"Ward ID starts with DEL-*?"}
            DD["Local delhi_data.ts"]
            HP["/api Proxy"]

            WM --> WP
            WP --> DEL
            DEL -->|Yes| DD
            DEL -->|No| HP
        end

        subgraph SOLAR["/app/solar"]
            SC["SolarCard"]
            SA["POST /solar/assess"]
            SC --> SA
        end

        subgraph CHAT["/app/chat"]
            CP["ChatPanel"]
            AC["POST /agent/chat"]
            CP --> AC
        end
    end

    subgraph BACKEND["FastAPI Backend — Port 8000"]
        direction TB

        subgraph PIPE["Pipeline — Landsat / LST"]
            PCORE["Pipeline Processing"]
            PA["Local Adapter"]
            PDATA["Local Files / Dictionary"]
            PCORE --> PA --> PDATA
        end

        subgraph SERVICES["Services — Recommendations / Advisories"]
            SCORE["Recommendation Services"]
            SLOCAL["Local Adapter"]
            SDATA["Local Files / Dictionary"]
            SCORE --> SLOCAL --> SDATA
        end

        subgraph AGENT["Agent — Strands / Mock"]
            ENGINE["Deterministic Engine"]
            TESTS["Tested"]
            ENGINE --> TESTS
        end
    end

    subgraph AWS["AWS Adapter — Written, Not Deployed"]
        ADAPTER["AWS Adapter"]
        S3["Amazon S3"]
        DDB["DynamoDB"]
        SNS["Amazon SNS"]
        LAMBDA["AWS Lambda"]
        CDK["AWS CDK Stacks"]

        ADAPTER --> S3
        ADAPTER --> DDB
        ADAPTER --> SNS
        ADAPTER --> LAMBDA
        CDK -.-> ADAPTER
    end

    B --> WM
    B --> SC
    B --> CP

    HP --> PCORE
    SA --> PCORE
    SA --> SCORE
    AC --> ENGINE

    PDATA -.->|Planned integration| ADAPTER
    SDATA -.->|Planned integration| ADAPTER

    classDef frontend fill:#DCEBFF,stroke:#3973AC,color:#16365C
    classDef local fill:#DDF5E3,stroke:#39965B,color:#174D2B
    classDef backend fill:#FFF0D5,stroke:#C58A22,color:#68440B
    classDef aws fill:#FBE2E2,stroke:#C65353,color:#702B2B
    classDef decision fill:#F0E2FF,stroke:#8756B3,color:#48266A

    class B,WM,WP,SC,CP frontend
    class DD,PDATA,SDATA,ENGINE,TESTS local
    class PCORE,PA,SCORE,SLOCAL,SA,AC,HP backend
    class ADAPTER,S3,DDB,SNS,LAMBDA,CDK aws
    class DEL decision
```

## Frontend

- **Heat:** Uses MapLibre for ward visualization. Delhi wards (`DEL-*`) read from `delhi_data.ts` without backend calls; other wards use the API proxy.
- **Solar:** `SolarCard` sends assessment requests to `POST /solar/assess`.
- **Chat:** `ChatPanel` sends messages to `POST /agent/chat`.

## Backend

FastAPI runs on port `8000` and contains three main components:

1. **Pipeline:** Processes Landsat and land surface temperature (LST) data.
2. **Services:** Provides recommendations and advisories.
3. **Agent:** Uses a deterministic engine with a Strands/mock integration.

The current implementation uses local adapters backed by files and dictionaries.

## AWS Integration

The AWS adapter has been written but is not deployed. The planned infrastructure includes:

- Amazon S3 for object storage.
- DynamoDB for structured data.
- Amazon SNS for notifications.
- AWS Lambda for serverless execution.
- AWS CDK for infrastructure provisioning.

Dotted arrows indicate planned integration, not active production connections.


**Key design decisions:**
- **Value envelope** (`core/envelope.py`): every context value carries class, source, dates, resolution, confidence and assumption IDs. Missing data is `unavailable` — **never 0**.
- **Parameters** (`config/params.default.yaml`): every tunable number is a `P-*` entry. Code never hard-codes them.
- **Policy as data** (`seed/policy/*.json`): subsidy tiers, tariffs, checklists are records, not code.
- **Adapters** (`adapters/`): every external dependency has `local` and `aws` implementations selected by `RUNTIME`.
- **The agent never computes numbers**: replies are templates over tool outputs; any number not in tool outputs triggers one regeneration, then a template fallback.


## 📜 License

Released under the **MIT License**. See [`LICENSE`](LICENSE) for details.

**Data attribution:** Landsat data is courtesy of the U.S. Geological Survey. Other datasets (WorldPop, ESA WorldCover, OpenStreetMap, NASA FIRMS, India Meteorological Department) have their own terms. See [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) for full attribution.

**Delhi administrative zones:** Based on Municipal Corporation of Delhi (MCD) zonal boundaries. Population figures are estimates. ΔLST values are illustrative and based on Landsat-derived urban heat patterns for Delhi NCT.
