# README — CoolRoof Planner + Heat Intelligence + SuryaCheck

> A geospatial decision-support platform for urban heat management, cool-roof prioritisation, rooftop-solar assessment (PM Surya Ghar), and environmental monitoring — powered by AWS serverless infrastructure with local-first development.

---

## 📋 Project Overview

This system analyses satellite-derived Land Surface Temperature (LST) from Landsat 8/9 to help Indian cities tackle urban heat. It provides:

- **Ward-level heat ranking** — configurable scoring with sensitivity analysis
- **Building-level cool-roof prioritisation** — benefit-per-rupee ranking
- **SuryaCheck** — rooftop-solar assessment with PM Surya Ghar subsidy, payback ranges, and PDF reports
- **Heat intelligence** — heat-type classification, driver attribution, evidence-backed recommendations
- **Heat-dome forecast** — NWP ensemble-based early warning (forecast signal)
- **Fire detection** — satellite (FIRMS) + staff-reported incident workflow
- **Environmental monitoring** — Habitat Pressure Index for protected areas, land degradation tracking
- **Bilingual AI agent** — Hindi/English conversational assistant (AWS Strands + Bedrock)
- **Public advisories** — approved bilingual text + TTS audio (Deepgram EN / Amazon Polly HI)

---

## 🛠️ Prerequisites

### System Requirements

| Requirement | Version |
|---|---|
| **Python** | 3.11+ |
| **Node.js** | 18+ (for frontend) |
| **Docker** | 24+ (with Docker Compose) |
| **GDAL** | 3.6+ (for rasterio) |
| **Make** | GNU Make |
| **Git** | 2.30+ |

### Optional (for AWS deployment)

| Requirement | Notes |
|---|---|
| **AWS CLI** | Configured with appropriate credentials |
| **AWS CDK** | `npm install -g aws-cdk` |
| **AWS Account** | With requester-pays enabled for Landsat |
| **Bedrock access** | Model access for the AI agent |

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repo-url>
cd coolroof
```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 3. Frontend Setup

```bash
cd frontend
npm install
cd ..
```

### 4. Environment Configuration

```bash
# Copy the example environment file
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Runtime mode: local (default) or aws
RUNTIME=local

# Optional: For LLM features (agent chat)
# If not set, a deterministic mock is used
ANTHROPIC_API_KEY=

# Optional: For TTS features
# If not set, silent WAV stubs are used
DEEPGRAM_API_KEY=

# Optional: For Hindi TTS
# If not set, text-only output
AWS_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# Optional: For fire detection
FIRMS_MAP_KEY=

# City configuration (default: Pune)
CITY=pune
```

### 5. Seed Data

```bash
# Load seed policy data (PM Surya Ghar subsidy, test tariff, checklist)
make seed
```

---

## ▶️ Running the Application

### Local Development (Default)

```bash
# Start both backend and frontend
make dev
```

This runs:
- **Backend API** at `http://localhost:8000` (FastAPI with uvicorn)
- **Frontend** at `http://localhost:5173` (Vite dev server)
- **Health check** at `http://localhost:8000/health`

No AWS credentials required. All external services use local adapters:
- S3 → `./data/` folder
- DynamoDB → SQLite
- LLM → Deterministic mock (or Anthropic API if key is set)
- TTS → Silent WAV stub (or Deepgram/Polly if keys are set)
- Notifications → `./data/outbox/*.json`

### Docker Compose

```bash
# Start with Docker
docker compose up

# Or with optional MinIO (S3) and DynamoDB Local
docker compose --profile full up
```

### Individual Services

```bash
# Backend only
make api

# Frontend only
make frontend

# Run the heat pipeline on the mini city fixture
make pipeline-mini
```

---

## 🧪 Testing

### Run All Tests

```bash
make test
```

### Specific Test Categories

```bash
# Unit tests only
make test-unit

# Property-based tests (hypothesis)
make test-property

# Golden fixture tests (SuryaCheck, agent conversations)
make test-golden

# Linting
make lint

# Type checking
make typecheck

# All CI checks (lint + typecheck + test)
make ci
```

### Mini City Fixture

The test suite includes a synthetic "mini city" with:
- 12 wards (GeoJSON)
- ~500 building footprints (Parquet)
- Population grid (GeoTIFF)
- 3 synthetic LST scenes
- NDVI/BSI yearly series with known trends
- FIRMS fire sample data
- NWP ensemble data with a planted heat-dome event

All module tests run against this fixture offline.

---

## 📁 Project Structure

```
coolroof/
├── README.md                    # This file
├── Makefile                     # Build commands
├── docker-compose.yml           # Docker services
├── .env.example                 # Environment template
├── pyproject.toml               # Python project config
│
├── docs/                        # Documentation
│   ├── SPEC.md                  # Build specification
│   ├── GAPS.md                  # Unverified items tracker
│   ├── DEMO.md                  # Demo walkthrough
│   └── DATA_SOURCES.md          # Data source docs
│
├── config/
│   ├── params.default.yaml      # All P-* parameters
│   └── cities/<city>.yaml       # Per-city config
│
├── rules/v1/                    # Immutable versioned rules
│   ├── rules.json               # Recommendation rules
│   ├── evidence.json            # Evidence registry
│   ├── cooling_options.json     # Cooling catalog
│   ├── heat_type_briefs.json    # Authority briefs
│   ├── advice.json              # Advisory whitelist
│   ├── glossary.json            # Hindi/English glossary
│   └── templates/{en,hi}/*.j2   # Advisory templates
│
├── seed/policy/                 # Seed policy data
│   ├── subsidy_pm_surya_ghar.json
│   ├── tariff_TEST-DISCOM.json
│   ├── checklist_generic.json
│   └── imd_heatwave_criteria.json
│
├── packages/
│   ├── core/                    # Shared foundations
│   ├── adapters/                # Local/AWS adapters
│   ├── pipeline/                # Batch processing (M1–M14, M15, M16, M24, M23, M43)
│   ├── services/                # Request-time services (M17–M37)
│   ├── agent/                   # Strands agent (M33+34)
│   └── api/                     # FastAPI app + routers
│
├── frontend/                    # React + Vite + MapLibre
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── i18n/
│   └── playwright/              # E2E tests
│
├── infra/                       # AWS CDK stacks
│   └── stacks/
│
├── tests/
│   ├── unit/
│   ├── property/
│   ├── golden/
│   └── fixtures/mini_city/
│
└── data/                        # (gitignored) Local data store
```

---

## 🌐 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `RUNTIME` | No | `local` | `local` or `aws` — selects adapter implementations |
| `CITY` | No | `pune` | Default city slug |
| `ANTHROPIC_API_KEY` | No | — | Enables LLM agent (otherwise mock) |
| `DEEPGRAM_API_KEY` | No | — | Enables English TTS (otherwise silent stub) |
| `AWS_REGION` | No | — | AWS region for Polly, Bedrock, etc. |
| `AWS_ACCESS_KEY_ID` | No | — | AWS credentials (for `RUNTIME=aws`) |
| `AWS_SECRET_ACCESS_KEY` | No | — | AWS credentials (for `RUNTIME=aws`) |
| `FIRMS_MAP_KEY` | No | — | NASA FIRMS API key for fire detection |
| `DATABASE_URL` | No | `sqlite:///data/coolroof.db` | SQLite path for local DocStore |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## 🏗️ AWS Deployment

### Prerequisites

1. AWS CLI configured with appropriate permissions
2. AWS CDK installed: `npm install -g aws-cdk`
3. Bedrock model access enabled
4. Requester-pays enabled for Landsat S3 bucket

### Deploy

```bash
# Bootstrap CDK (first time only)
cd infra
cdk bootstrap

# Deploy all stacks
cdk deploy --all

# Or deploy individual stacks
cdk deploy CoolRoofDataStack
cdk deploy CoolRoofPipelineStack
cdk deploy CoolRoofApiStack
cdk deploy CoolRoofFrontendStack
cdk deploy CoolRoofAlertsStack
cdk deploy CoolRoofMonitoringStack
```

### Post-Deployment

```bash
# Set RUNTIME to aws
export RUNTIME=aws

# Run golden tests against deployed API
make test-golden API_URL=https://<api-gateway-url>

# Verify canary
make canary
```

---

## 📖 Key Concepts

### Value Envelope
Every data value carries provenance metadata (source, date, class, confidence, staleness).

### Ward Context
The central data record per ward — all features merged with provenance. Built only by M8.5.

### SuryaCheck
The rooftop-solar assessment pipeline: location → solar resource → roof suitability → system size → subsidy → payback.

### Evidence Tags
- `[V]` — Verified against source
- `[R]` — Recalled; needs checking
- `[NV]` — Needs verification
- `[ASSUME]` — Modelling assumption (configurable parameter)

### Local-First
All external services have local adapters. The full prototype runs with `make dev` without any cloud credentials.

---

## ⚠️ Important Caveats

- **LST ≠ air temperature.** Landsat measures surface temperature at a late-morning satellite pass (~100 m native resolution, resampled to 30 m).
- **Individual roofs cannot be resolved** from satellite thermal data. Rankings use neighbourhood heat + area + population + cost.
- **Cool-roof coefficients are placeholders** (scenario ranges) until calibrated by a 10–20 roof pilot.
- **M43 heat-dome outputs are "forecast signals"**, not official warnings. Official IMD warnings always take precedence.
- **M23/M24 outputs are "indicators"**, not diagnoses or biodiversity-loss measurements.
- **The synthetic tariff (TEST-DISCOM) is for testing only.** Real DISCOM tariffs require hand-curation from ERC/DISCOM orders.

---

## 📄 Related Documentation

| Document | Description |
|---|---|
| [CoolRoof_Build_Spec_v0.3.md](CoolRoof_Build_Spec_v0.3.md) | Full build specification (source of truth) |
| [PRD.md](PRD.md) | Product Requirements Document |
| [SPEC.md](SPEC.md) | Technical Specification |
| [TASKS.md](TASKS.md) | Implementation Plan & Task Tracker |
| [AGENTS.md](AGENTS.md) | AI Agent Coding Instructions |
| `docs/GAPS.md` | Unverified items and data gaps |
| `docs/DEMO.md` | Demo walkthrough script |
| `docs/DATA_SOURCES.md` | Data source documentation |

---

## 🤝 Credentials the Human Must Provide

The agent stubs these until provided:

| Credential | Purpose |
|---|---|
| AWS account (requester-pays enabled) | Landsat S3 access |
| Bedrock model access (or `ANTHROPIC_API_KEY`) | AI agent |
| Deepgram API key | English TTS |
| AWS Polly access | Hindi TTS |
| FIRMS MAP_KEY | Fire detection |
| Real DISCOM tariff records (verified) | Payback calculations |
| City ward boundary layer | Analysis unit |

---

## 📜 License

TBD — see project configuration.
