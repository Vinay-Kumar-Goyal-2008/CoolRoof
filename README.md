# CoolRoof — urban heat prioritisation + rooftop solar (SuryaCheck)

**Which roofs should a city cool first — and can your home go solar?**

CoolRoof ranks a city's wards and roofs for cool-roof action from Landsat surface temperature, and
gives households a locality-aware rooftop-solar check (PM Surya Ghar subsidy, payback range,
Hindi/English assistant, PDF summary). It is **Windows-native and local-first**: it runs fully offline
on a synthetic city with no cloud credentials. The AWS target (Strands Agents + Bedrock, Lambda,
API Gateway, S3, DynamoDB, CDK) is written but **has not been deployed yet**.

> **Read this first if you are new:** [What is built](#what-is-built-vs-the-original-plan) →
> [What is left](#what-is-left-start-here) → [Run it](#run-it-locally).
> The original plan lives in `Agent/` (`CoolRoof_Build_Spec_v0.3.md` is the source of truth,
> `TASKS.md` the stage plan). Where this README or `docs/GAPS.md` disagrees with those files,
> **this README and GAPS win**: the build moved to Windows-native tooling and a reduced scope.

## Repository layout

| Folder | Contents |
|---|---|
| `backend/` | Python 3.12 (uv). `packages/core` contracts · `adapters` local/AWS interfaces · `pipeline` batch modules · `services` request-time modules · `agent` assistant · `api` FastAPI. Plus `config/`, `rules/v1/`, `seed/policy/`, `assets/fonts/`, `scripts/`, `tests/` |
| `frontend/` | Next.js 15 + MapLibre, English/हिंदी, Playwright tests (`e2e/`) |
| `infra/` | AWS CDK (Python): `DataStack` (S3 + 12 DynamoDB tables), `ApiStack` (Lambda container + API Gateway) |
| `docs/` | `GAPS.md` (every deviation + open item, **read it**), `DEMO.md` (3-minute video script) |
| `Agent/` | The original specs (spec v0.3, PRD, SPEC, TASKS, AGENTS), `SCOPE_DEFERRED.md`, and the installed Claude skills (`Agent/.claude/skills`) |

## What is built, vs the original plan

Every module in the plan now has code and tests. What remains is **deployment, live-service verification and real data** (below).

| Stage | Plan | Status |
|---|---|---|
| 0 Scaffold | core, adapters, API, fixtures, CI | **Done** (CI workflow, docker-compose, `.env.example`) |
| 1 Heat pipeline | M1–M14, tile builder | **Done** incl. ΔLST PMTiles |
| 2 SuryaCheck | M25–M32 | **Done** incl. NASA POWER + pvlib fallback, shared cache, roof outline |
| 3 Agent + PDF + UI | M33–M36, M38, M39, M41 | **Done** (all 11 screens); 30-turn EN+HI golden suite; Strands engine unrun |
| 4 Heat intelligence | M15–M21, M37, Cognito | **Done** (drivers, 10 rules, advisories + TTS, readiness, alerts hub, Cognito verification) |
| 5 Hazards + forecast | M22, M43 | **Done**: FIRMS pipeline + incidents; forecast with Open-Meteo adapter, IMD-style check, hindcast scoring |
| 6 Environment | M23, M24 | **Done** (habitat pressure index, degradation trends) |
| 7 AWS deploy | CDK stacks | 2 of 6 stacks written; **never deployed** (owner's step) |
| 8 Data-gated | electricity forecast, GMM, CNN, Aurora | Not started (needs data) |

### Module by module

| Module | State | Notes |
|---|---|---|
| M1+2 location | ✅ | `GET/POST /locations/resolve` (point, name in EN/HI, polygon) |
| M3+4 Landsat | ✅ fixture · ⚠️ live | Planetary Computer / USGS S3 sources never run against the real services |
| M5–M8, M8.5, M9 | ✅ | LST, ΔLST, hotspots, footprints, population, context builder (+ `extras` for lists), priority with rank intervals |
| M10–M14 | ✅ code · ⚠️ output | Costs and °C effects stay `unavailable` until `P-CM2`, `P-DALB`, `P-KCOOL`, `P-KIND` are verified. Admins can set them with a source (`PUT /admin/config` or the console) |
| M15 heat type | ✅ | Rule-based; no GMM second opinion |
| M16 drivers | ✅ | 3×3 blocks, VIF, OLS + XGBoost/SHAP, spatial CV, Moran's I, bootstrap CI, "associated with" |
| M17 recommendations | ✅ | 10 rules incl. R-RD/FR/DG, official-warning precedence, cooling-option matching. Evidence mostly placeholder (grade C) |
| M18+19 advisories + TTS | ✅ | Compose from whitelisted advice, optional grounded rewrite, approval workflow, EN Deepgram / HI Polly (stub offline), cache, cap |
| M20+21 readiness | ✅ / ⛔ | Facility table + prompts HOSP/EXAM/COOL/ELEC. Electricity *forecast* mode not built (data-gated) |
| M22 fire | ✅ | FIRMS normalise → dedupe → cluster → classify → persistent suppression → alert rule; staff incidents with 2-person confirmation; fixture + live source |
| M23 habitat | ✅ | HPI per protected area, PA_FIRE_*/PRESSURE_RISE warnings, wording denylist |
| M24 degradation | ✅ | Mann–Kendall + Sen, rain adjustment, leave-one-year-out stability, transition alerts |
| M25–M32 SuryaCheck | ✅ | PVGIS → NASA POWER+pvlib → stale cache; true-up credit not modelled |
| M33+34 agent | ⚠️ | Deterministic engine tested; **Strands engine (Bedrock / Anthropic) written, never run**. 17 tools, keyword intents, grounding check, refusals |
| M35+36 PDF | ✅ | Noto Sans + Devanagari, vector roof outline |
| M37 alerts | ✅ | Dedupe, rate limit, expiry, approval gates, audit, hashed subscriptions, one publish per language (SNS adapter untested) |
| M38 dashboard | ✅ | 11 screens: map with ΔLST raster, hotspots, facilities, fire, protected areas, degradation colouring; ward panel (drivers, readiness, land); solar with roof sketch; assistant; alerts & forecast with audio; planner console |
| M39 API | ✅ | Every route in spec §6 (plus `/layers`, `/tiles`, `/audio`, `/admin/params`, `/admin/metrics`) |
| M40–M42 | ⚠️ | DocStore/BlobStore done; auth = API keys + `X-Actor` or Cognito Bearer; metrics = CloudWatch EMF lines + `/admin/metrics` (no alarms/dashboards yet) |
| M43 heat-dome | ⚠️ | Fixture ensemble correct; live Open-Meteo path is temperature-only (capped at `watch`); hindcast scoring code ready, not run on real archives |

### Tests

`uv run poe test` — backend unit, property, golden and end-to-end suites (~6 min; the e2e files run the real API, the
pipeline, advisories, alerts, incidents, auth and the 30-turn conversation). `ruff` clean, `mypy` clean.
`npm run test:e2e` in `frontend/` — 5 Playwright tests in real Chromium (needs API on :8000 and the app running).

## What is left (start here)

Everything that can run offline is done. In order:

1. **Deploy to AWS** (needs credentials + Docker): `cd infra; npx cdk deploy --all`, load data with
   `RUNTIME=aws python -m scripts.run_pipeline --city mini_city`. Fix what the first real deploy exposes. The
   `S3BlobStore`, `DynamoDocStore`, `SNSNotifier`, `SecretsManagerSecrets`, `PollyTTS` and Cognito paths have never run.
   Not yet written: Step Functions/Fargate pipeline stack, Amplify, EventBridge schedules for `scripts/run_jobs.py`, CloudWatch alarms.
2. **Run the Strands engine** against Bedrock (`BEDROCK_MODEL_ID`, `RUNTIME=aws`) or Anthropic (`ANTHROPIC_API_KEY`); rerun the golden
   conversation through it and confirm the grounding fallback.
3. **Verify live services**: Open-Meteo, NASA POWER, FIRMS (`FIRMS_MAP_KEY`) and PVGIS field names are [R] and only mocked in tests. Add
   Z500 climatology to lift the live forecast above `watch`; run `m43_eval` on archived 2022/2024 heatwave forecasts.
4. **Replace placeholders with verified values** (data work): `P-CM2`, `P-DALB/KCOOL/KIND`, `P-GCOST`, real DISCOM tariff and
   net-metering records, the evidence registry, advice lines reviewed by a native Hindi speaker and the health authority.
5. **Run a real city.** `backend/config/cities/pune.yaml` is a stub: it needs ward layer, footprints, WorldPop, WorldCover, DEM,
   facilities, protected areas and a hot-season `trend_series`. Validate LST against MODIS.
6. **Data-gated extras**: electricity forecast mode, GMM heat-type second opinion, CNN, Aurora.

## Run it locally

Windows-native: no GDAL, GTK or `make` needed. Requires `uv`, Node 18+.

```powershell
cd backend
uv sync --all-extras
uv run poe pipeline-mini     # run the heat pipeline on the synthetic city → backend/data/
uv run poe api               # http://localhost:8000/docs

cd ..\frontend
npm install
npm run dev                  # http://localhost:3000  (proxies /api to :8000)
```

Other tasks: `uv run poe` lists them (`ci`, `test`, `lint`, `typecheck`, `fixtures`, `seed`).
Copy `backend/.env.example` to `backend/.env` (it sets `PLANNER_API_KEY=dev-planner-key` and `ADMIN_API_KEY=dev-admin-key` for the
planner console; other keys are optional and stubs are used without them). Jobs by hand: `uv run python -m scripts.run_jobs fire|heatdome|stale`;
set `ENABLE_JOBS=true` to schedule them inside the API.
Browser tests: start the API and `npm start`, then `npm run test:e2e` in `frontend/`.

**Demo inputs:** 70 m² roof, 400 units/month, ₹1,80,000 quote → 3 kW, ₹78,000 subsidy, payback range.
(300 units correctly gives 2 kW / ₹60,000.) Script: `docs/DEMO.md`.

## Deploy to AWS

```powershell
cd infra
python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt
npm install                              # project-local CDK CLI
npx cdk bootstrap ; npx cdk deploy --all # needs AWS credentials and a running Docker engine
cd ..\backend
$env:RUNTIME="aws"; $env:S3_BUCKET="<bucket from stack output>"
uv run python -m scripts.run_pipeline --city mini_city
```

Set `BACKEND_URL=<ApiUrl>` for the frontend (`next.config.mjs` proxies `/api/*` to it).

## How the code is organised (read before changing things)

* **Value envelope** (`core/envelope.py`): every context value carries class, source, dates, resolution, confidence
  and assumption IDs. Missing data is `unavailable` with a reason — **never 0**.
* **Parameters** (`config/params.default.yaml`): every tunable number is a `P-*` entry with an evidence status.
  Code never hard-codes them. `[NV]` entries are `null` on purpose and degrade outputs to "unavailable".
* **Policy as data** (`seed/policy/*.json` → DocStore): subsidy tiers, tariffs, checklists are records, not code.
* **Adapters** (`adapters/`): every external dependency has a `local` and an `aws` implementation selected by `RUNTIME`.
* **Ward Context** is the only thing downstream modules and the agent read (`pipeline/m085_context.py`): to expose a new
  value, register a table and a `FieldSpec`. Field names are restricted to the spec schema.
* **The agent never computes numbers** (`core/grounding.py` + `agent/m33_agent.py`): replies are templates over tool
  outputs; any number not in tool outputs triggers one regeneration, then a template fallback.
* **Wording rules** (`core/wording.py`): "surface temperature at a late-morning satellite pass", "associated with",
  "indicator", "forecast signal, not an official warning" — enforced by tests.
* **Synthetic fixture** (`backend/tests/fixtures/mini_city`, regenerate with `uv run poe fixtures`): 12 wards with
  planted archetypes (see `scripts/make_mini_city.py`) so every module has known answers.

## Honest limits

LST is not air temperature and individual roofs cannot be resolved from Landsat; cool-roof coefficients and costs are
unverified and left empty; the demo tariff is synthetic; heat-dome output is a forecast signal, not an official warning;
nothing has been validated against ground truth or run on a real city.

Some documents in `Agent/` (`README`, `SPEC`, `AGENTS`, `TASKS`) still describe the original Linux-style plan (Python 3.11,
`make`, WeasyPrint, React + Vite, repo root `coolroof/`). `docs/GAPS.md` §1 lists each deviation; they have not been rewritten.
