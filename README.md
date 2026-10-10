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

Status of the nine stages in `Agent/TASKS.md`:

| Stage | Plan | Status |
|---|---|---|
| 0 Scaffold | core, adapters, API skeleton, fixtures, CI | **Done** (local adapters; AWS adapters written, untested) |
| 1 Heat pipeline | M1–M14, tile builder | **Done except the PMTiles tile builder** |
| 2 SuryaCheck | M25–M32 | **Done**, with gaps listed below |
| 3 Agent + PDF + UI MVP | M33–M36, M38, M39, M41 | **Mostly done**: 5 of 11 screens, no 30-turn golden suite |
| 4 Heat intelligence | M15, M16, M17, M18+19, M20+21, M37, Cognito | **M15 and a compact M17 only**; rest deferred |
| 5 Hazards + forecast | M22, M43 | **M43 on fixture data only**; M22 deferred |
| 6 Environment | M23, M24 | **Deferred** |
| 7 AWS deploy | CDK stacks, deploy | **2 of 6 stacks written, synthesise, never deployed** |
| 8 Data-gated | electricity forecast, GMM, CNN, Aurora | Not started |

### Module by module

| Module | State | Notes |
|---|---|---|
| M1+2 location | ✅ | Point/name/polygon → ward, state, DISCOM; grid fallback. **No `/locations/resolve` HTTP route yet** |
| M3+4 Landsat | ✅ fixture · ⚠️ live | Planetary Computer and USGS S3 sources written, never run against the real services |
| M5 LST, M6 heat | ✅ | USGS L2 ST only; rural-reference ΔLST, hotspots, persistence, leave-one-year-out stability |
| M7 footprints, M8 population | ✅ | Cleaning, ward aggregates, WorldPop allocation, neighbourhood-heat exposure |
| M8.5 context builder | ✅ | Declarative `FieldSpec`s, value envelopes, staleness job, JSON-schema validated |
| M9 priority | ✅ | Percentile / z-score, Dirichlet rank intervals, leave-one-out, property test |
| M10–M14 roofs, cool-roof ranges, plan | ✅ code · ⚠️ output | Costs and °C effects are **unavailable until `P-CM2`, `P-DALB`, `P-KCOOL`, `P-KIND` are verified** |
| M15 heat type | ✅ | Rule-based, precedence-ordered, authority brief. No GMM second opinion |
| M16 driver attribution | ⛔ deferred | |
| M17 recommendations | ⚠️ compact | 7 rules, evidence registry mostly placeholder (grade C → never Tier 1). Rules for deferred modules not built |
| M18+19, M20+21, M22, M23, M24, M37 | ⛔ deferred | See `Agent/SCOPE_DEFERRED.md` for the reasoning and what changes elsewhere |
| M25 solar resource | ⚠️ | Fixture + PVGIS path (untested live). **NASA POWER + pvlib fallback not built**; cache is in-memory |
| M26 roof suitability | ⚠️ | Usable area, suitability flag, questions. `outline_changed` flag only partly implemented |
| M27+28 size, M29 subsidy | ✅ | Subsidy is a generic tier calculator over a policy record; staleness warn/block |
| M30+31 payback | ✅ | Net metering + net billing, scenario triples, status codes, 2.0-year golden fixture. True-up credit not modelled |
| M32 orchestrator | ✅ | Pure, idempotent (`input_hash`), partial results, golden JSON |
| M33+34 agent | ⚠️ | Deterministic engine works and is tested; **Strands engine (Bedrock / Anthropic) is written but never run**. 9 tools, grounding check, refusals |
| M35+36 checklist, PDF | ✅ | fpdf2 + HarfBuzz, Noto Sans + Devanagari. No SVG roof outline; no 24 h URL expiry / 7-day lifecycle enforcement locally |
| M38 dashboard | ⚠️ | 5 screens: map + ranking, ward panel (heat type, recommendations, roofs), SuryaCheck, assistant, PDF. **No ΔLST raster layer / PMTiles; screens 9 and 11 not built** |
| M39 API | ⚠️ | health, wards, ward context / heat-type / buildings / recommendations, plan, heat-dome, solar, policy, checklist, PDF, sessions, chat. **Missing:** `locations/resolve`, `analysis/heat` (202), `admin/*` |
| M40 storage, M41 auth, M42 monitoring | ⚠️ | DocStore + BlobStore done. Auth = anonymous sessions + API-key dependency (no planner routes, no Cognito). Monitoring = JSON logs + `/health` (no CloudWatch metrics/alarms) |
| M43 heat-dome | ⚠️ | Ensemble criteria correct on the planted fixture. **No Open-Meteo/GFS adapter, no climatology job, no hindcast** |

### Tests

`uv run poe test` — **199 backend tests** (unit, property, golden, end-to-end through the real API incl. Hindi PDF
text and the grounded agent), ~5 minutes. `ruff` clean, `mypy --strict` clean (relaxed only for the numerical
pipeline modules, whose pandas stubs are noisy). `npm run test:e2e` — 2 Playwright tests in real Chromium.

## What is left (start here)

Work in this order; it follows the value for a working demo and the open risks.

1. **Deploy to AWS** (needs credentials + Docker): `cd infra; npx cdk deploy --all`, then load data with
   `RUNTIME=aws python -m scripts.run_pipeline --city mini_city`. Fix whatever the first real deploy exposes.
   The `S3BlobStore`, `DynamoDocStore`, `SNSNotifier`, `SecretsManagerSecrets` and `PollyTTS` adapters have never run.
2. **Run the Strands engine against Bedrock** (set `BEDROCK_MODEL_ID` with `RUNTIME=aws`, or `ANTHROPIC_API_KEY` locally).
   Verify the grounding check and fallback behave with a real model, then write the 30-turn golden conversation suite (en + hi).
3. **Close the cheap API gaps:** `GET /locations/resolve`, `POST /analysis/heat` + `GET /analysis/heat/{id}`, `admin/*`.
4. **Replace placeholders with verified values** (this is data work, not code): coating cost `P-CM2`, cool-roof
   coefficients `P-DALB/KCOOL/KIND` (literature + a 10–20 roof pilot), `P-GCOST`, real DISCOM tariff and net-metering
   records (only a *synthetic* tariff exists), and the evidence registry. Each is listed in `docs/GAPS.md` §3–4.
5. **Run a real city.** `backend/config/cities/pune.yaml` is a stub: it needs the ward layer, building footprints,
   WorldPop, WorldCover, DEM and facilities. Then validate LST against MODIS.
6. **Finish the planned UI/data bits:** PMTiles / ΔLST raster layer (tile builder), NASA POWER + pvlib solar fallback,
   SVG roof outline in the PDF, remaining dashboard screens.
7. **Deferred modules** (M16, M18+19, M20+21, M22, M23, M24, M37, Cognito): the specs are intact; `Agent/SCOPE_DEFERRED.md`
   explains how to bring one back (add the module, register its table with a `FieldSpec`, add router + tests from its Verify bullets).
8. **Stage 7 remainder:** pipeline (Step Functions / Fargate), frontend (Amplify), alerts (EventBridge/SNS), monitoring
   (CloudWatch, Budgets) stacks.

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
Copy `backend/.env.example` to `backend/.env` to add optional keys (all are optional; stubs are used otherwise).
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
