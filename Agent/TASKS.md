# TASKS — Implementation Plan

> **Version:** 1.0 — Derived from [CoolRoof_Build_Spec_v0.3.md](CoolRoof_Build_Spec_v0.3.md)
> **Date:** 2026-10-10
> **Legend:** ⬜ = Not Started | 🔄 = In Progress | ✅ = Done

---

## Stage 0 — Scaffold

> **Done when:** `make dev` serves `/health`; fixtures load; lint + type check + tests pass.

### 0.1 Repository Structure
- [ ] ⬜ Create top-level files: `README.md`, `Makefile`, `docker-compose.yml`, `.env.example`, `pyproject.toml`
- [ ] ⬜ Create `docs/` folder with `SPEC.md`, `GAPS.md`, `DEMO.md`, `DATA_SOURCES.md`
- [ ] ⬜ Create `config/params.default.yaml` with every P-* parameter ID (value|null, status, source)
- [ ] ⬜ Create `config/cities/pune.yaml` (bbox, season, UTM EPSG, DISCOM map, weight profile)
- [ ] ⬜ Create `rules/v1/` with placeholder `rules.json`, `evidence.json`, `cooling_options.json`, `heat_type_briefs.json`, `advice.json`, `glossary.json`, `templates/{en,hi}/` directory structure
- [ ] ⬜ Create `seed/policy/` with `subsidy_pm_surya_ghar.json` (F1/F3 [V]), `tariff_TEST-DISCOM.json` (synthetic), `checklist_generic.json`, `imd_heatwave_criteria.json`

### 0.2 Core Package (`packages/core/`)
- [ ] ⬜ `envelope.py` — Value envelope class with all 7 value classes
- [ ] ⬜ `ids.py` — ID generation for building, session, alert, advisory, forecast, dedupe_key
- [ ] ⬜ `enums.py` — All enums from §4.4 (heat_type, suitability, fire_class, trend_class, degradation_signal, habitat_pressure, heatdome_risk, alert_status, payback_status, eligibility, etc.)
- [ ] ⬜ `errors.py` — Error hierarchy matching §4.5 error codes (400, 401, 403, 404, 409, 422, 424, 429, 502, 504)
- [ ] ⬜ `params.py` — Parameter registry and YAML loader for P-* values
- [ ] ⬜ `provenance.py` — Provenance tracking (source, date, class badge, assumption IDs)
- [ ] ⬜ `grounding.py` — Number grounding library (Latin/Devanagari digits, ₹/Rs, lakh/crore, Indian grouping)
- [ ] ⬜ `i18n.py` — Indian number formatter (en/hi locale, ₹ formatting)
- [ ] ⬜ Write unit tests for every core module

### 0.3 Adapters (`packages/adapters/`)
- [ ] ⬜ `blobstore.py` — Interface + `LocalBlobStore` (./data/) + `S3BlobStore`
- [ ] ⬜ `docstore.py` — Interface + `SQLiteDocStore` (JSON columns, PK/SK) + `DynamoDocStore`
- [ ] ⬜ `llm.py` — Interface + `AnthropicLLM` + `MockLLM` (keyword tool calls) + `BedrockLLM`
- [ ] ⬜ `tts.py` — Interface + `DeepgramTTS` + `PollyTTS` + `SilentWavStub`
- [ ] ⬜ `notifier.py` — Interface + `FileNotifier` (./data/outbox/) + `SNSNotifier`
- [ ] ⬜ `scheduler.py` — Interface + `APSchedulerLocal` + `EventBridgeScheduler`
- [ ] ⬜ `secrets.py` — Interface + `DotEnvSecrets` + `SecretsManagerSecrets`
- [ ] ⬜ `landsat_source.py` — Interface + `PlanetaryComputerSource` + `FixtureSource` + `USGSS3Source`
- [ ] ⬜ `nwp_source.py` — Interface + `OpenMeteoSource` + `FixtureNWPSource` + `GFSS3Source`
- [ ] ⬜ Implement `RUNTIME=local|aws` env var selection logic
- [ ] ⬜ Write adapter tests (each adapter against its interface contract)

### 0.4 FastAPI Skeleton
- [ ] ⬜ `packages/api/app.py` — FastAPI init + Mangum handler
- [ ] ⬜ `packages/api/routers/health.py` — `GET /health` returning status + versions
- [ ] ⬜ CORS config (limited to frontend origin)
- [ ] ⬜ Request ID middleware + structured JSON logging

### 0.5 Mini-City Fixtures
- [ ] ⬜ `tests/fixtures/mini_city/wards.geojson` — 12 synthetic wards
- [ ] ⬜ `tests/fixtures/mini_city/buildings.parquet` — ~500 footprints
- [ ] ⬜ `tests/fixtures/mini_city/population.tif` — Population grid
- [ ] ⬜ `tests/fixtures/mini_city/lst_scenes/` — 3 small synthetic LST scenes
- [ ] ⬜ `tests/fixtures/mini_city/ndvi_bsi_series/` — Yearly NDVI/BSI with known trends
- [ ] ⬜ `tests/fixtures/mini_city/firms_sample.csv` — FIRMS fire data
- [ ] ⬜ `tests/fixtures/mini_city/nwp_ensemble.json` — NWP sample with planted heat-dome event

### 0.6 Docker & CI
- [ ] ⬜ `docker-compose.yml` — api + frontend containers
- [ ] ⬜ `Makefile` — `make dev`, `make test`, `make lint`, `make typecheck`
- [ ] ⬜ CI config: lint (ruff), type check (mypy), tests (pytest), schema validation

---

## Stage 1 — Heat Pipeline

> **Done when:** Mini city produces ranked wards with components + rank interval; roof list with ranges; CSV export; all Verify tests pass.

### 1.1 Location (M1+2)
- [ ] ⬜ Point-in-polygon on ward boundaries → `LocationRef`
- [ ] ⬜ `make_valid` and slivers handling
- [ ] ⬜ EPSG:4326 storage, UTM computation
- [ ] ⬜ City → state → DISCOM lookup table
- [ ] ⬜ Edge cases: outside wards (404), gaps/overlaps, renumbered wards (`boundary_version`)
- [ ] ⬜ Verify: every demo centroid falls in exactly one ward; area within 1–2% of city area

### 1.2 Landsat Acquisition & Preprocessing (M3+4)
- [ ] ⬜ STAC search (pystac-client) with bbox, season window, platform filters
- [ ] ⬜ Windowed COG reads (ST_B10, ST_QA, QA_PIXEL, SR bands)
- [ ] ⬜ QA masking (fill, dilated cloud, cirrus, cloud, shadow, snow via QA_PIXEL bits)
- [ ] ⬜ Apply scale/offset from STAC `raster:bands` (never hardcode)
- [ ] ⬜ Drop pixels with ST_QA uncertainty > P-STQA
- [ ] ⬜ Reproject to city UTM, common 30 m grid (bilinear)
- [ ] ⬜ Output: masked ST stack, SR stack, scene manifest
- [ ] ⬜ Verify: valid-pixel % logged; low-observation wards flagged; 3-scene visual mask check

### 1.3 Land Surface Temperature (M5)
- [ ] ⬜ `lst_median = nanmedian(stack)`, `lst_p90`, `n_obs`, `iqr`
- [ ] ⬜ Per-year medians and per-scene `hot_flag = LST > city_p90`
- [ ] ⬜ Plausible-range filter with logging
- [ ] ⬜ Verify: water cooler than built-up; r(LST, NDVI) < 0; Spearman ρ vs MODIS ≥ P-MODIS-RHO

### 1.4 Heat / Heat-Island Analysis (M6)
- [ ] ⬜ ΔLST = LST − median(rural reference mask); reference mask from cropland/tree in 10–20 km ring
- [ ] ⬜ DEM elevation adjustment when relief is large
- [ ] ⬜ Area-weighted zonal stats per ward (mean, median, p90, max, std)
- [ ] ⬜ Hotspot detection (Gi* or percentile + connected components)
- [ ] ⬜ `persistence_w` = mean share of ward area in city top decile per scene
- [ ] ⬜ `heat_z_w = (ΔLST_w − μ)/σ`
- [ ] ⬜ Compute NDVI, NDBI, NDWI, BSI from SR bands
- [ ] ⬜ Output: `heat_features` table, `hotspots.parquet`
- [ ] ⬜ Verify: city mean z ≈ 0; hotspots match built/bare areas; Kendall τ with year leave-out

### 1.5 Building Footprints (M7)
- [ ] ⬜ Ingest, UTM reproject, repair, deduplicate, drop below min area
- [ ] ⬜ Assign to wards by centroid; compute aggregates (count, built fraction, roof area, density)
- [ ] ⬜ Stable `building_id = hash(dataset_id + geometry)`
- [ ] ⬜ Flag `buildings_incomplete` for sparse wards
- [ ] ⬜ Verify: built area vs WorldCover built class ratio on 3 wards; precision/recall on ~100 buildings

### 1.6 Population Exposure (M8)
- [ ] ⬜ WorldPop building-level allocation: `pop_b = Σ pop_cell * area(b∩cell)/Σ area(b'∈cell)`
- [ ] ⬜ Ward population with optional official-figure scaling (capped)
- [ ] ⬜ `exposed_pop_w = Σ pop_b * 1[heat_local_b ≥ P-TAU]`
- [ ] ⬜ Vulnerability (age) = `unavailable` unless reliable data
- [ ] ⬜ Verify: building sum ≈ grid total (±1%); MAPE vs official; mass conservation

### 1.7 Ward Context Builder (M8.5)
- [ ] ⬜ Merge all feature tables → provenance-tagged `ward_context` per ward
- [ ] ⬜ Write Value Envelopes for every field
- [ ] ⬜ Compute `data_quality` section (counts + `context_confidence`)
- [ ] ⬜ Handle conflicting sources (documented precedence, `alt_value`)
- [ ] ⬜ Build `roof_context` records
- [ ] ⬜ Storage: PK `city#ward_id`, SK `ctx#<date>` + S3 snapshot
- [ ] ⬜ Staleness job: flip fields past `stale_after` to `stale`
- [ ] ⬜ Verify: 100% JSON-schema validation; 10-ward audit; removing dataset → `unavailable` not `0`

### 1.8 Ward Priority Score (M9)
- [ ] ⬜ Within-city percentile normalisation (z-score for <30 wards)
- [ ] ⬜ Components: H, P, E, V, R, F
- [ ] ⬜ Formula: `Need = (a_H·H + a_P·P + a_E·E + a_V·V)/Σa; Priority = Need·(0.5+0.5·R)·F`
- [ ] ⬜ Missing variable: drop, renormalise, record `variables_used`
- [ ] ⬜ Dirichlet sensitivity (1000 draws) → rank interval + top-10 stability
- [ ] ⬜ Leave-one-variable-out analysis
- [ ] ⬜ Verify: hand-computed toy city; monotonicity test; sensitivity report

### 1.9 Roof Prioritisation (M10)
- [ ] ⬜ Eligibility filter (min area, footprint confidence, ward not `buildings_incomplete`)
- [ ] ⬜ `Score_b = f(local_heat_b, pop_b·φ_b, roof_area_b, cost_b)` — benefit per rupee
- [ ] ⬜ `local_heat_b` = neighbourhood pixel mean (not the roof's own temperature)
- [ ] ⬜ Verify: top 20 roofs plausible on imagery; ranks stable under ±20% cost change

### 1.10 Cool-Roof Impact, Cost, People Protected (M11+12+13)
- [ ] ⬜ Scenario triples (low/base/high) from literature [NV]
- [ ] ⬜ `ΔT_pix,b = P-KCOOL · P-DALB · f_b`
- [ ] ⬜ `ΔT_indoor = P-KIND · P-DALB · 1[top floor]`
- [ ] ⬜ `Cost_b = roof_area_b · P-CM2 · (1 + P-PREP)`
- [ ] ⬜ `Protected_b = pop_b · φ_b`
- [ ] ⬜ `BC_b = Protected_b · heat_weight_b / Cost_b`
- [ ] ⬜ Budget: greedy knapsack by BC_b
- [ ] ⬜ If P-CM2 missing → output benefit only, refuse BC ratio
- [ ] ⬜ Verify: cost linearity; φ bounds; tornado sensitivity

### 1.11 Municipal Action Ranking (M14)
- [ ] ⬜ Rank wards by Priority, buildings by BC
- [ ] ⬜ Apply budget constraint
- [ ] ⬜ CSV export with columns: rank, ward, building_id, action, cost_range, people_protected_range, confidence, assumptions
- [ ] ⬜ Verify: same config+data → identical list (hash); total cost ≤ budget

### 1.12 Tile Builder
- [ ] ⬜ Generate PMTiles for ΔLST/LST raster layers
- [ ] ⬜ Ward priority choropleth tiles

---

## Stage 2 — SuryaCheck

> **Done when:** Golden JSON for 3 locations; 3 kW → ₹78,000; payback fixture = 2.0 yr; missing tariff/consumption statuses correct.

### 2.1 Solar Resource (M25)
- [ ] ⬜ PVGIS PVcalc with `peakpower=1, loss=0` (loss-free baseline)
- [ ] ⬜ Fallback chain: PVGIS → NASA POWER + pvlib → cached cell → `unavailable`
- [ ] ⬜ Cache key: `round(lat,1), round(lon,1), tilt, az`
- [ ] ⬜ Scenario losses: `Y_s = Y_0 · (1 − P-LOSS_s)`
- [ ] ⬜ Output: `specific_yield{low,base,high}`, `monthly[12]`, meta
- [ ] ⬜ Verify: PVGIS vs POWER at 5 cities; plausible-band check; fixture responses

### 2.2 Roof Suitability (M26)
- [ ] ⬜ Area from user polygon or footprint, recomputed server-side in UTM
- [ ] ⬜ `A_usable = A_roof · P-U{low,base,high}` or user-stated free area (class USER)
- [ ] ⬜ Suitability flags: suitable / check_obstructions / unsuitable / unknown
- [ ] ⬜ User questions: ownership, roof type, shading, shared roof, free area
- [ ] ⬜ Flag `outline_changed` if ratio exceeds threshold
- [ ] ⬜ Verify: computed vs user area on 20 homes; 2 UTM zones; all flag paths

### 2.3 System Size & Generation (M27+28)
- [ ] ⬜ `kW_area = A_usable / P-AKW`
- [ ] ⬜ `kW_load = Σ monthly_kWh / Y_base`
- [ ] ⬜ `kW_cap = DISCOM cap [NV, optional]`
- [ ] ⬜ `kW_max = min(...)` with `limiting_factor = argmin`
- [ ] ⬜ `kW_rec = floor(kW_max / P-KWSTEP)·P-KWSTEP`
- [ ] ⬜ Generation: `Gen_1[s] = kW_rec · Y_s · (1 − P-LID)`, `Gen_t = Gen_1·(1−P-DEG)^(t−1)`
- [ ] ⬜ Monthly yields, F2 slab guidance shown alongside
- [ ] ⬜ No consumption → return `kW_area` upper bound + ask for bill
- [ ] ⬜ Verify: every limiting branch; property test (more area never reduces kW_max)

### 2.4 PM Surya Ghar Subsidy (M29)
- [ ] ⬜ Policy as data in DocStore (`policy#subsidy#ALL#ALL`)
- [ ] ⬜ Residential formula: `S(c) = 30000·min(c,2) + 18000·max(0, min(c,3)−2)`
- [ ] ⬜ GHS/RWA formula: `S = 18000·c`
- [ ] ⬜ State top-up: tri-state `unknown | none_verified | amount`
- [ ] ⬜ Eligibility: `unconfirmed` until F6 verified
- [ ] ⬜ Staleness: age > P-STALE-POLICY → warning; > P-HARD-POLICY → blocks PDF (424)
- [ ] ⬜ Output: `policy_version`, `effective_date`, `source_url`, `rule_id`, record hash
- [ ] ⬜ Verify: table tests for c ∈ {0.5, 1, 2, 2.5, 3, 3.5, 10}; stale record blocks PDF

### 2.5 Net Metering & Payback (M30+31)
- [ ] ⬜ Tariff records: `policy#tariff#<state>#<discom>` (slabs, fixed charge)
- [ ] ⬜ Settlement records: `policy#netmetering#…` (net_metering|net_billing, banking, export rate)
- [ ] ⬜ Monthly simulation over H years × {low,base,high}
- [ ] ⬜ Net metering: `net = C − G − bank; billed = max(net,0); bank = max(−net,0)`
- [ ] ⬜ Net billing: `self = min(G·s, C); billed = C − self; credit += (G−self)·export_rate`
- [ ] ⬜ `Payback_simple = NetCost/Savings[1]; Payback_cum = min T: Σ(Savings−O&M−inverter) ≥ NetCost`
- [ ] ⬜ Headline shown only if tariff + settlement present and fresh, DISCOM supported, gross cost = user, consumption = user
- [ ] ⬜ Otherwise return `payback_unavailable_*` status
- [ ] ⬜ Verify: golden arithmetic fixture (₹8/kWh flat, 2.0 yr payback); banking edge cases; higher tariff → shorter payback

### 2.6 SuryaCheck Orchestrator (M32)
- [ ] ⬜ Chain: M1+2 → M25 → M26 → M27+28 → M29 → M30+31
- [ ] ⬜ Each step returns `ok | partial | unavailable`; failed step doesn't abort later steps
- [ ] ⬜ Response: 200 with `status complete|partial`, `missing[]`, `next_questions[]`
- [ ] ⬜ 424 only if `require_policy=true` (PDF)
- [ ] ⬜ 502 only if solar unavailable and nothing else computable
- [ ] ⬜ Pure function; `input_hash` makes it idempotent
- [ ] ⬜ Every number has class (FACT/ASSUMPTION/USER/ESTIMATE) + locale display strings
- [ ] ⬜ Verify: golden JSON for 3 locations in different DISCOMs; contract test (UI, agent, PDF match)

---

## Stage 3 — Agent + PDF + UI MVP

> **Done when:** Demo: pick ward → rank → roof → solar → chat (hi) → PDF; Playwright happy path; 0 ungrounded numbers.

### 3.1 Strands Agent (M33+34)
- [ ] ⬜ Define 6 MVP tools with typed pydantic args and JSON output:
  - `get_ward_context`, `get_solar_assessment`, `get_subsidy_rules`, `get_checklist`, `generate_application_pdf`, `request_user_input`
- [ ] ⬜ System prompt with language detection (UI toggle + Devanagari detection + Hinglish handler)
- [ ] ⬜ Turn flow: load session → confirm language → confirm location → call tools → draft with `{{tool.field}}` placeholders → grounding check → citations
- [ ] ⬜ Grounding check: extract all numbers (Latin/Devanagari digits, ₹/Rs, lakh/crore), verify each in session tool outputs; regenerate once → fallback to template
- [ ] ⬜ Rules: no number unless from tool; never submit applications; refuse medical/legal; session turn/token caps
- [ ] ⬜ Glossary at `rules/glossary.json`
- [ ] ⬜ Verify: 30-turn golden suite (en + hi), 100% grounding; red-team prompts

### 3.2 Checklist & PDF (M35+36)
- [ ] ⬜ Checklist template: `{state, discom, version, items[{id, title_i18n, detail_i18n, documents[], applies_to[], source_url, verification}]}`
- [ ] ⬜ Selection: state+DISCOM → state → generic (all `needs_official_check`)
- [ ] ⬜ PDF sections: header, SVG roof outline, system table with badges, subsidy with provenance, payback range, checklist, applicant details (consent only), footer
- [ ] ⬜ WeasyPrint container with Noto Sans + Noto Sans Devanagari
- [ ] ⬜ Startup self-test: extract rendered Hindi text and compare
- [ ] ⬜ Presigned URL valid 24h; lifecycle expiry 7 days
- [ ] ⬜ No Aadhaar, bank details, or documents collected; consent notice
- [ ] ⬜ Verify: extracted text = source text (en + hi); every number traces; visual regression on 3 PDFs

### 3.3 Dashboard / Map MVP (M38 — screens 1–3, 5–8, 10)
- [ ] ⬜ React + Vite + MapLibre GL + PMTiles project setup
- [ ] ⬜ i18next with en/hi translations
- [ ] ⬜ Screen 1: City / ward picker
- [ ] ⬜ Screen 2: Heat map with ΔLST/LST raster + LST disclaimer
- [ ] ⬜ Screen 3: Ward ranking with component bars, rank interval, confidence
- [ ] ⬜ Screen 5: Roof list (ranked buildings in a ward)
- [ ] ⬜ Screen 6: Roof detail (cool-roof ranges)
- [ ] ⬜ Screen 7: SuryaCheck card
- [ ] ⬜ Screen 8: Agent chat (EN/हिंदी)
- [ ] ⬜ Screen 10: PDF download
- [ ] ⬜ Provenance UI: class badge on every number, hover for source/date/resolution
- [ ] ⬜ Self-hosted PMTiles basemap
- [ ] ⬜ Accessibility: keyboard-navigable, colour-blind-safe palette
- [ ] ⬜ Playwright tests for happy path + unavailable states

### 3.4 Backend API (M39)
- [ ] ⬜ All routers from §4.3 (locations, analysis, wards, solar, agent, documents, alerts, fire, environment, forecast, admin, health)
- [ ] ⬜ pydantic v2 models → OpenAPI generation
- [ ] ⬜ Body size limits, GeoJSON validation
- [ ] ⬜ `POST /analysis/heat` → 202 with execution id
- [ ] ⬜ Agent route: finish within ~29s or 504 with idempotent retry
- [ ] ⬜ Verify: contract tests against OpenAPI; auth matrix tests; idempotency tests

### 3.5 Auth MVP (M41)
- [ ] ⬜ Anonymous sessions: 128-bit random id with TTL
- [ ] ⬜ API key on planner routes
- [ ] ⬜ Role capabilities: anon (SuryaCheck, agent, PDF, read)
- [ ] ⬜ All writes as immutable versions with author + timestamp

---

## Stage 4 — Heat Intelligence

> **Done when:** Recommendations with evidence and not_evaluated; approved advisory with audio; readiness prompts; alerts in outbox.

### 4.1 Heat-Type Classification (M15)
- [ ] ⬜ Gate: required fields unavailable/stale → `undetermined`
- [ ] ⬜ City-relative percentiles
- [ ] ⬜ Precedence-ordered rules (6 types: undetermined, not_hot, episodic, dense_built_low_green, open_bare_or_industrial, chronic_other)
- [ ] ⬜ Confidence: `min(feature conf) × margin`
- [ ] ⬜ Hotspot polygon typing
- [ ] ⬜ Authority brief: per heat type from `heat_type_briefs.json` — template-rendered with ward values
- [ ] ⬜ Optional GMM second opinion (SageMaker Processing): k=2..6 by BIC, 200 bootstraps, ARI check
- [ ] ⬜ Verify: synthetic wards for every label; θ ± 0.05 flip-rate; expert review of 10 wards

### 4.2 Heat Tracing / Driver Attribution (M16)
- [ ] ⬜ N×N pixel blocks (N=3), water removed
- [ ] ⬜ Features: NDVI, NDBI, built fraction, roof fraction, distance to water, elevation, slope
- [ ] ⬜ VIF filter (NDVI/NDBI collinearity → keep one or first PC)
- [ ] ⬜ OLS (standardised coefficients, robust SE) + GBM with SHAP
- [ ] ⬜ Disagreement flagging (`unstable`)
- [ ] ⬜ Spatial CV: leave out 2 km tiles with buffer; report R², Moran's I
- [ ] ⬜ Ward attribution: `mean SHAP_f` (°C, direction, bootstrap CI)
- [ ] ⬜ Always attach `unobserved: ["anthropogenic_heat", "industrial_process_heat", "roof_material"]`
- [ ] ⬜ Verify: sign sanity; year-to-year rank stability; wording always "associated with"

### 4.3 Recommendation Engine (M17)
- [ ] ⬜ Versioned artefacts: `rules.json`, `evidence.json`, `cooling_options.json`
- [ ] ⬜ Rule schema: `{id, intervention, required_fields, condition, impact_model_ref, cost_model_ref, evidence_ref, evidence_grade, caveats, audience, excludes}`
- [ ] ⬜ Implement all 10 rules: R-CR-01, R-SO-01, R-CP-01, R-EX-01, R-GR-01, R-RD-01, R-EC-01, R-HD-01, R-FR-01, R-DG-01
- [ ] ⬜ `cooling_options.json` entries with i18n names, type, cost_band, evidence_ref, context matching
- [ ] ⬜ Evaluation: unavailable/stale → `not_evaluated`; fired → evidence + grade
- [ ] ⬜ Ranking: Tier 1 (quantified) > Tier 2 (qualitative); Grade C never in Tier 1 without override
- [ ] ⬜ CI rejects rules with empty `evidence_ref`
- [ ] ⬜ Verify: fire/no-fire/missing tests per rule; counterfactual test; byte-identical reproducibility

### 4.4 Public Awareness + TTS (M18+19)
- [ ] ⬜ Template selection by (advisory type, heat_type, official level or M43 level)
- [ ] ⬜ Slot filling: ward name, level, validity, advice lines from `advice.json`
- [ ] ⬜ EN and HI text generation
- [ ] ⬜ Optional LLM tone rewrite with grounding check (on failure → keep template)
- [ ] ⬜ Approval workflow: `draft → approved → published → expired | withdrawn`
- [ ] ⬜ Forecast-based advisories: staff audience only; public needs explicit approval + "forecast signal" text
- [ ] ⬜ TTS adapter: `deepgram` for EN, `polly` for HI; cache by sha256; sentence splitting; daily cap
- [ ] ⬜ Provider failure → text only + log
- [ ] ⬜ Verify: template lint; 100% number grounding; 20 Hindi messages reviewed; unapproved/expired never delivered

### 4.5 Hospital / Emergency & Electricity Readiness (M20+21)
- [ ] ⬜ Facility counting per ward; `nearest_hospital_m` from exposed-pop-weighted centroid
- [ ] ⬜ `facilities_per_10k_exposed = 10000 · count_within(P-COVER) / exposed_pop`
- [ ] ⬜ Implement all 5 prompts: HOSP-01, HOSP-02, EXAM-01, COOL-01, ELEC-01
- [ ] ⬜ Electricity forecast mode (Phase 3, data-gated): seasonal naive baseline, regression on air temp, rolling MAPE gate
- [ ] ⬜ Verify: spot-check 20 facilities; rule tests; MAPE gate

### 4.6 Alerts & Notifications (M37)
- [ ] ⬜ Producers: M18+19, M20+21, M22, M23, M24, M43
- [ ] ⬜ Audiences: staff (auto_info allowed) + public (requires `approved`)
- [ ] ⬜ SNS: one topic per city+audience; message attributes with filter policies
- [ ] ⬜ Dedupe by `alert_id`; rate limit P-ALERT-RATE; `valid_until` enforcement; DLQ + alarm
- [ ] ⬜ Subscriptions: `POST /alerts/subscriptions` (email confirmation; addresses stored hashed)
- [ ] ⬜ In-app: `GET /alerts?ward=` for banner
- [ ] ⬜ Verify: unapproved/expired never sent; filter tests; full audit trail

### 4.7 Cognito (AWS only)
- [ ] ⬜ Wire Cognito for planner/admin roles
- [ ] ⬜ City-scoped role support

---

## Stage 5 — Hazards + Forecast

> **Done when:** Planted heat-dome detected with expected first_day; FIRMS → classified events; incident report → confirm → approved public alert.

### 5.1 Fire Detection & Alerts (M22)
- [ ] ⬜ **Satellite path:** Poll FIRMS every P-FIRE-POLL minutes (VIIRS + MODIS NRT)
- [ ] ⬜ Normalise confidence: `low | nominal | high`
- [ ] ⬜ Idempotent dedupe; cluster per overpass within pixel scale
- [ ] ⬜ Classify by WorldCover majority: vegetation_fire (forest_fire) / agricultural_burning_candidate / urban_thermal_anomaly_candidate / unclassified
- [ ] ⬜ Suppress persistent sources (kilns, flares)
- [ ] ⬜ Alert rule: high-confidence vegetation_fire within P-FIRE-RADIUS of ward/hospital/protected area
- [ ] ⬜ **Incident path:** `POST /fire/incidents` (staff report → `structure_fire_reported`); `POST /fire/incidents/{id}/confirm` → `structure_fire_confirmed`
- [ ] ⬜ Optional `IncidentFeedAdapter` for fire-service feed
- [ ] ⬜ Satellite urban candidate near reported incident → linked (never auto-confirmed)
- [ ] ⬜ Public alerts only for confirmed incidents via M18+19 approval
- [ ] ⬜ Heat-linked fire risk advisory: M17 R-FR-01
- [ ] ⬜ Context patch: `hazards.fire_events_30d`, `hazards.fire_incidents_30d`
- [ ] ⬜ Verify: replay 1 month (precision/recall); hand-label ~50 events; idempotency; latency metric; incident workflow tests

### 5.2 Heat-Dome / Extreme-Heat Forecast (M43)
- [ ] ⬜ Daily scheduled run (after NWP forecast update)
- [ ] ⬜ Ingest: D16 (Tmax, Z500 from Open-Meteo/GFS); D17 (climatology: mean, std, p90 by DOY)
- [ ] ⬜ Per-member, per-day: T_anom, hotT, Z_anom, ridge, signal
- [ ] ⬜ Event detection: consecutive signal days ≥ P-HD-DAYS
- [ ] ⬜ p_event = share of members with event
- [ ] ⬜ Risk classification: none | watch | elevated | high
- [ ] ⬜ Output: forecast record (forecast_id, city, issued_at, source, risk, p_event, first_day, duration, tmax_range, criteria_params, official_warning_ref)
- [ ] ⬜ Patch `heat.heatdome_risk` / `heatdome_ref` on ward context
- [ ] ⬜ Staff alert via M37 when risk ≥ elevated
- [ ] ⬜ Trigger M17 (R-HD-01, R-EX-01, R-RD-01, R-FR-01) and M20+21
- [ ] ⬜ Ward downscaling: rank wards by `heat_z` (relative modifier only, no invented ward temp)
- [ ] ⬜ Optional IMD-style heatwave check on forecast Tmax (labelled "meets IMD-style criterion", not IMD warning)
- [ ] ⬜ Edge cases: source down → `unavailable`; deterministic-only → `low_confidence`
- [ ] ⬜ Hindcast script for past hot seasons (2022, 2024 Indian heatwaves)
- [ ] ⬜ Official warning manual entry: `POST /admin/official-warnings`
- [ ] ⬜ Verify: hindcast metrics (hit rate, FAR, Brier); P-HD-* sensitivity; wording test ("forecast signal"); planted fixture detected

---

## Stage 6 — Environment

> **Done when:** Synthetic series → expected classes; HPI monotonic; wording denylist passes.

### 6.1 Land / Soil Degradation Tracking (M24)
- [ ] ⬜ Trend job (separate state machine, reuses M3+4 code)
- [ ] ⬜ Per hot season (≥ P-TREND-MIN years): per-ward medians over non-built, non-water, cloud-free pixels for NDVI, BSI, LST
- [ ] ⬜ Same sensors (L8/9) every year; valid coverage < P-COVMIN → year missing
- [ ] ⬜ Mann–Kendall (serial-correlation handling) + Sen's slope per indicator per ward and protected area
- [ ] ⬜ Rainfall adjustment (if D19 CHIRPS available): regress NDVI on seasonal rainfall, test residual trend
- [ ] ⬜ Land Degradation Signal: count adverse significant trends (NDVI ↓, BSI ↑, LST ↑) → none/weak/moderate/strong
- [ ] ⬜ Fully built wards (> P-BUILT-NA) → `not_applicable`
- [ ] ⬜ Static context: `bare_fraction` (WorldCover), `soc_mean` + texture (SoilGrids)
- [ ] ⬜ Store yearly series in `curated/soil/series.parquet`; recompute each season
- [ ] ⬜ Transition alert: signal rises by ≥ 1 class → planner-only alert
- [ ] ⬜ Feeds M17 R-DG-01 and M23
- [ ] ⬜ Labelling: every output says "indicator, not diagnosis"
- [ ] ⬜ Verify: synthetic series (up/down/flat/noisy) → expected classes; class stability (drop 1 year); visual check 3 wards

### 6.2 Biodiversity: Habitat Pressure Index (M23)
- [ ] ⬜ Scope: per protected area (WDPA or OSM fallback) + per ward touching it
- [ ] ⬜ 4 indicators: I_fire (M22), I_loss (D18 Hansen / NDVI-drop fallback), I_veg (M24 NDVI trend), I_heat (M5/M24 LST trend)
- [ ] ⬜ `HPI = Σ w_i · pct_i` (percentile across all PAs in region, or own history if single PA)
- [ ] ⬜ Classes: low | moderate | high (P-HPI-THETA); `insufficient_data` if < 2 indicators
- [ ] ⬜ Warnings: PA_FIRE_INSIDE / PA_FIRE_NEAR (event-driven); PA_HABITAT_PRESSURE_RISE (yearly)
- [ ] ⬜ Optional GBIF species-recorded context (shown as "species recorded here", never loss count)
- [ ] ⬜ Message: names area, indicator(s), period, source + "habitat pressure indicator, unverified — not a measured biodiversity loss"
- [ ] ⬜ Denylist: blocks species-loss wording
- [ ] ⬜ Licence handling: WDPA terms → query only or OSM; neither → skip
- [ ] ⬜ Verify: inside/edge/outside tests; index monotonicity; dataset metadata at 100%; wording denylist

### 6.3 Phase 2 Agent Tools
- [ ] ⬜ Add Phase 2 tools to agent: `get_roof_context`, `get_heat_analysis`, `get_recommendations`, `get_readiness`, `get_alerts`, `get_advisory`, `get_heatdome_forecast`, `get_habitat_pressure`, `get_degradation`
- [ ] ⬜ Update golden agent suite with new tool coverage

### 6.4 Dashboard Screens 4, 9, 11
- [ ] ⬜ Screen 4: Ward panel (context, heat type + authority brief, drivers, recommendations, readiness, degradation)
- [ ] ⬜ Screen 9: Alerts and forecast (heat-dome banner + panel, fire events, PA alerts)
- [ ] ⬜ Screen 11: Planner console (approve advisories, log fire incidents)
- [ ] ⬜ Map layers: hotspots by heat type, facilities, fire events + incidents, protected areas by HPI class, degradation signal, heat-dome forecast banner

---

## Stage 7 — AWS Deploy

> **Done when:** Same golden tests pass against deployed API; canary green.

### 7.1 CDK Stacks
- [ ] ⬜ `infra/stacks/data.py` — S3 buckets, DynamoDB tables (PITR, encryption)
- [ ] ⬜ `infra/stacks/pipeline.py` — Step Functions, Lambda (container), Fargate (optional)
- [ ] ⬜ `infra/stacks/api.py` — API Gateway (REST), Lambda handlers (Mangum)
- [ ] ⬜ `infra/stacks/frontend.py` — Amplify hosting
- [ ] ⬜ `infra/stacks/alerts.py` — SNS topics, EventBridge schedules (FIRMS, M43, freshness, staleness)
- [ ] ⬜ `infra/stacks/monitoring.py` — CloudWatch dashboards, alarms, AWS Budgets

### 7.2 Deployment
- [ ] ⬜ Switch `RUNTIME=aws` and verify all adapters use AWS implementations
- [ ] ⬜ Run golden tests against deployed API
- [ ] ⬜ Set up synthetic canary on `/solar/assess`
- [ ] ⬜ Configure requester-pays for Landsat in us-west-2
- [ ] ⬜ Verify: same golden tests pass; canary green; cost budget within limits

---

## Stage 8 — Data-Gated (Optional)

> **Done when:** Only if data, licences, or keys are provided; else documented in `docs/GAPS.md`.

### 8.1 Optional Modules
- [ ] ⬜ M20+21 electricity forecast mode (requires utility load data)
- [ ] ⬜ M15 GMM clustering on SageMaker (requires enough ward data)
- [ ] ⬜ Roof-type classification CNN (requires labelled training data)
- [ ] ⬜ Aurora PostGIS (only if DuckDB-spatial is outgrown)

### 8.2 Documentation
- [ ] ⬜ Document all gaps in `docs/GAPS.md`
- [ ] ⬜ Document all [NV] items that need verification
- [ ] ⬜ Update `docs/DEMO.md` with full demo script

---

## Summary Tracker

| Stage | Total Tasks | Done | Status |
|---|---|---|---|
| 0 — Scaffold | 37 | 0 | ⬜ Not Started |
| 1 — Heat Pipeline | 42 | 0 | ⬜ Not Started |
| 2 — SuryaCheck | 33 | 0 | ⬜ Not Started |
| 3 — Agent + PDF + UI MVP | 28 | 0 | ⬜ Not Started |
| 4 — Heat Intelligence | 36 | 0 | ⬜ Not Started |
| 5 — Hazards + Forecast | 28 | 0 | ⬜ Not Started |
| 6 — Environment | 23 | 0 | ⬜ Not Started |
| 7 — AWS Deploy | 10 | 0 | ⬜ Not Started |
| 8 — Data-Gated | 6 | 0 | ⬜ Not Started |
| **TOTAL** | **243** | **0** | ⬜ **Not Started** |
