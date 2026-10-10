# GAPS — unverified items, data gaps and deviations

Tracks everything the build could not verify or had to decide (spec rule 9, Appendix B).
Status: **OPEN** needs a human; **DECIDED** implemented as described, review welcome.

## 1. Deviations from Build Spec v0.3 (all DECIDED)

| # | Spec says | Built as | Why |
|---|---|---|---|
| D1 | Python 3.11 | Python 3.12 via `uv` | All Windows wheels verified on 3.12; Lambda supports 3.12 |
| D2 | `make dev` / GNU Make | `uv run poe <task>` (poethepoet) + `honcho` for API + frontend | Windows-native, no extra installer |
| D3 | WeasyPrint (GTK/Pango) | fpdf2 + uharfbuzz (Hindi shaping), PyMuPDF for text checks | WeasyPrint needs GTK on Windows |
| D4 | PDF test "extracted text = source text" | Compared after stripping control characters | Every PDF engine tested emits stray control codes at Devanagari conjuncts on extraction |
| D5 | React + Vite frontend | Next.js (separate `frontend/` folder) | Project owner's choice |
| D6 | Repo root `coolroof/` | `backend/` + `frontend/` + `docs/`; specs stay in `Agent/` | Project owner's choice |
| D7 | Denylist bans "loss", "diagnosis", "official warning" | Required phrases are exempt; negated terms allowed; rules scoped (e.g. "due to" only in driver text) | The spec's own required sentences contain the banned words |
| D8 | Subsidy formula `S(c)=30000·min(c,2)+…` in code | Stored as tiers in the policy record; code is a generic tiered calculator | Rule: no subsidy figure in application code |
| D9 | roof_context PK `ward#building_id` | PK `ward#<ward_id>`, SK `roof#<building_id>` + GSI | Spec key cannot list a ward's roofs |
| D10 | Error classes `ValidationError`, `TimeoutError` | `InputValidationError`, `UpstreamTimeoutError` | Avoid shadowing pydantic / built-ins |
| D11 | Glossary at `rules/glossary.json` (M33+34) vs `rules/v1/glossary.json` (§9) | `rules/v1/glossary.json` | Versioned rules folder |
| D12 | Tariff and settlement are separate records | Seed tariff file embeds settlement; seeding stores two records | Spec seed list names only the tariff file |
| D13 | `built_fraction` from footprints (M7) | WorldCover built share is primary, footprint share kept as `alt_value` | Footprints are patchy (spec M7 edge case); the mini city has ~500 footprints |
| D14 | `buildings_incomplete` when footprints cover <50 % of WorldCover built area | Relative to the city median (P-BLDG-INCOMPLETE) | Footprint datasets under-cover whole cities evenly |
| D15 | M33 default LLM via Strands | Deterministic mock by default; Strands engine (Bedrock on AWS, Anthropic locally) used only when a model/key is configured | Local-first; Strands path is written but **not exercised** without credentials |
| D16 | Screens 1–11 | 5 screens (map + ranking, ward panel with roofs, SuryaCheck, assistant, PDF) | Scope reduction, see `Agent/SCOPE_DEFERRED.md` |
| D17 | Hindi PDF fonts | Noto Sans (Latin) primary + Noto Sans Devanagari fallback, bundled in `backend/assets/fonts` | Devanagari font alone has no Latin glyphs |
| D18 | PMTiles raster basemap | Ward polygons on a plain background, hotspot outlines and roof footprints as GeoJSON | No external tile server; ΔLST raster tiles not built |

## 2. Parameters set as [ASSUME] typical values (DECIDED, review needed)

All values live in `backend/config/params.default.yaml` with source notes. Parameters marked
`added_by_implementation: true` are not in spec §11 but were needed to avoid hidden constants:
P-LST-RANGE, P-REF-RING, P-REF-MAXSLOPE, P-RELIEF, P-HOTSPOT-PCT, P-WARD-MINAREA,
P-BLDG-MINAREA, P-BLDG-CONF, P-BLDG-INCOMPLETE, P-POPSCALE-CAP, P-STALE-CONTEXT,
P-CTX-CRITICAL, P-W-DIRICHLET, P-SMALL-CITY, P-F, P-DRIVER-BLOCK, P-DRIVER-CV,
P-FIRE-CLUSTER, P-FIRE-PERSIST, P-TREND-ALPHA, P-SOLAR-BAND, P-OUTLINE-RATIO, P-HORIZON,
P-HD-HORIZON.

## 3. Values deliberately left null — [NV] (OPEN)

| Parameter | Effect while null | Needed from |
|---|---|---|
| P-DALB, P-KCOOL, P-KIND | Cool-roof °C effects shown as `unavailable` | Literature ranges (Appendix B item 8), 10–20 roof pilot |
| P-CM2 | Benefit only; benefit-per-cost ratio refused | Local coating cost schedule |
| P-GCOST | Payback headline needs user-supplied gross cost | Cited vendor / DISCOM cost schedule |

## 4. Facts and sources to verify (OPEN)

- F5 subsidy release timing (secondary source), F6 eligibility/documents/vendor/DCR rules, F7 net-metering terms per state.
- Real DISCOM tariff records (MSEDCL for Pune). Only the synthetic TEST-DISCOM tariff exists.
- IMD heatwave criteria in `seed/policy/imd_heatwave_criteria.json` are [R].
- Landsat C2 L2 scale/offset, QA bits, ST_QA meaning (Appendix B item 3) — code reads scale/offset from STAC metadata, never hard-codes them.
- Amazon Polly Hindi voice `Kajal` (neural) availability in the deployment region [R].
- Deepgram Aura-2 voice id `aura-2-thalia-en` [R].
- Pune ward boundary layer and dataset licences (buildings, WorldPop, WorldCover, DEM, WDPA).

## 5. Credentials not yet provided (stubs in use)

AWS account (requester-pays), Bedrock model access or `ANTHROPIC_API_KEY`, Deepgram key,
Polly access, FIRMS MAP_KEY.

## 6. Open items (OPEN)

* **AWS deployment was not run**: no credentials on the build machine (the owner deploys). `infra/` synthesises; Cognito, SNS, Polly, Bedrock, S3 and DynamoDB adapters are written but have never touched real AWS.
* Strands engine against Bedrock / Anthropic is untested (no keys). Agent behaviour is verified with the deterministic engine (30-turn EN+HI golden suite, red-team prompts). All 13 tools are registered with Strands.
* M17 evidence: only the PM Surya Ghar entry is real; the rest are placeholders marked NV (grade C, never Tier 1).
* **M43 live path is temperature-only**: Open-Meteo has no wired Z500 climatology, so live forecasts are labelled `criteria_mode: temperature_only`, low confidence, capped at `watch`. The full ridge criterion runs on the fixture / any source that provides Z500. Hindcast *scoring* (hit rate, FAR, Brier, parameter sensitivity) is built (`m43_eval.py`) but has not been run on archived real forecasts. Open-Meteo, NASA POWER and FIRMS field names are [R] and were only exercised against mocked responses.
* **M23 HPI** uses the NDVI-drop proxy for tree loss (Hansen GFC is not wired) and, for fewer than 3 protected areas, fixed trend scales instead of percentiles across areas. I_fire has no multi-year history in the fixture, so the fixture HPI uses 3 indicators.
* **M24** needs a real hot-season series per ward (`trend_series`); the fixture is synthetic. Mann–Kendall uses the Hamed–Rao correction only when the detrended series is serially correlated.
* **M20+21** electricity *forecast* mode (peak-demand regression) is data-gated and not built; readiness prompts never use bed, stock or demand data.
* **M16** uses 3×3 blocks and OLS+XGBoost/SHAP; NDVI is kept and NDBI dropped by the VIF filter. Not validated by an expert check on real wards.
* **ΔLST tiles** are PNG PMTiles for zoom 10–14 built with Pillow (no tippecanoe). Served through the API with Range support; on AWS serve the object from S3/CloudFront instead.
* Roof outline: drawn on a 2 m grid sketch (no basemap) and converted to a lon/lat polygon around the demo location; a real map-based tracer is not built.
* Real-city run, MODIS validation, verified costs/coefficients (`P-CM2`, `P-DALB`, `P-KCOOL`, `P-KIND`, `P-GCOST`), real DISCOM tariffs: data work, still open.
* Stage 8 (electricity forecast, GMM second opinion, CNN, Aurora) is data-gated and not started. Pipeline (Step Functions/Fargate), Amplify, EventBridge/SNS and CloudWatch alarm stacks are deployment work.
* Property/golden suites take ~6 minutes in total (`uv run poe test`).

## 7. Added in the completion pass (DECIDED)

* D19 `POST /analysis/heat` runs the pipeline in a background thread locally (a Step Functions/Fargate task on AWS); the run state lives in the `runs` table, a second trigger returns 409.
* D20 `X-Actor` names the person behind a shared API key so the two-person rules work without Cognito; with `COGNITO_ISSUER` + `COGNITO_CLIENT_ID` set, Bearer tokens map `admin`/`planner` groups to roles.
* D21 Admin parameter edits (`PUT /admin/config`) need a value, an evidence status and a source; they are stored as versioned overrides and re-applied at startup. Setting `P-CM2` unlocks the budget plan.
* D22 New parameters: `P-GAMMA` (power temperature coefficient, fallback only) and `P-BUILT-DENSE` (built form for cooling-option matching), both [ASSUME].
* D23 Fixture fire data is evaluated "as of" its last pass (not today) so the 30-day window is meaningful.
* D24 Public agent sessions only see public alerts/advisories; staff items (fire candidates, forecast signals, transitions) are never exposed to the assistant.
