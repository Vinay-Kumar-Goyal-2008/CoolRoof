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

## 6. Open items from the final build (OPEN)

* **AWS deployment was not run**: no AWS credentials on the build machine. `infra/` synthesises (`cdk synth`); deploy with `npx cdk deploy --all`, then load data with `RUNTIME=aws python -m scripts.run_pipeline`.
* Strands engine against Bedrock / Anthropic is untested (no keys). Agent behaviour verified with the deterministic engine only.
* M17 is a compact implementation (7 rules); evidence entries other than the PM Surya Ghar policy are placeholders marked NV and cannot enter Tier 1.
* M43 runs on the fixture ensemble only; the Open-Meteo adapter is not written. Hindcast validation is not built.
* M41 auth is API-key only (no Cognito). Planner-write routes (advisories, fire incidents) are deferred.
* ΔLST is evaluated only on the synthetic city; no real-city run (needs ward layer, buildings, WorldPop, WorldCover, DEM).
* Property/golden suites run ~5 minutes in total (`uv run poe test`).
