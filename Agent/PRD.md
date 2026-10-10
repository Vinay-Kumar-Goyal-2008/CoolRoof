# PRD — CoolRoof Planner + Heat Intelligence + SuryaCheck

> **Version:** 1.0 — Derived from [CoolRoof_Build_Spec_v0.3.md](CoolRoof_Build_Spec_v0.3.md)
> **Date:** 2026-10-10

---

## 1. Product Overview

### 1.1 What Is Being Built

**CoolRoof Planner + Heat Intelligence + SuryaCheck** is a geospatial decision-support platform that combines satellite-derived Land Surface Temperature (LST) analysis, building-level cool-roof prioritisation, rooftop-solar assessment (under PM Surya Ghar), heat intelligence (heat typing, driver attribution, forecasting), environmental monitoring (fire, habitat pressure, land degradation), and a bilingual (Hindi/English) AI agent — all backed by AWS serverless infrastructure with a fully functional local-first development mode.

For a given city with ward boundaries, the system:

1. Computes hot-season **Land Surface Temperature (LST)** from Landsat 8/9.
2. Joins LST with building footprints and population data.
3. **Ranks wards**, then **buildings**, for cool-roof intervention using explicit, configurable scoring.
4. **Types and traces** each ward's heat pattern (rule-based classification + correlational driver attribution).
5. **Recommends interventions** backed by evidence (cool-roof, solar, green cover, cooling points, economical cooling options).
6. **Forecasts heat-dome / extreme-heat risk** from open NWP data.
7. Issues **approved bilingual advisories** (text + audio via Deepgram EN / Amazon Polly HI).
8. Detects and alerts on **fires** (satellite + urban/structure-fire incidents) and **habitat pressure** in protected areas.
9. Tracks **land-degradation indicators** (NDVI, BSI, LST trends) per ward.
10. Gives homeowners a **locality-aware rooftop-solar assessment** (PM Surya Ghar subsidy, payback range, Hindi/English agent-guided checklist, and downloadable PDF).

### 1.2 Problem Statement

Indian cities face severe urban heat, but municipal planners lack actionable, ward-level data to target cool-roof and cooling interventions cost-effectively. Homeowners eligible for the PM Surya Ghar rooftop-solar subsidy face a complex application process with no locality-aware guidance. Emergency and environment officers need early warning of heat-dome events, fires, and environmental degradation — currently fragmented across multiple systems.

**This product solves:**

| Problem | How |
|---|---|
| No ward-level heat prioritisation | LST from Landsat → ranked wards with components, confidence, and sensitivity |
| No building-level roof targeting | Building footprints + population exposure + cost → benefit-per-rupee ranking |
| Complex solar subsidy process | SuryaCheck: automated size → subsidy → payback → checklist → PDF, bilingual agent |
| No heat-type or causal understanding | Rule-based heat typing + GBM/SHAP driver attribution per ward |
| No early heat-dome warning | NWP ensemble-based forecast signal (1–10 days), deterministic criteria |
| Fragmented fire alerts | Satellite (FIRMS VIIRS/MODIS) + staff-reported structure fires → classified, deduplicated alerts |
| No habitat pressure tracking | Habitat Pressure Index per protected area (fire, tree loss, NDVI/LST trends) |
| No land degradation monitoring | Multi-year trend analysis → Land Degradation Signal per ward |
| Language barrier for citizens | Bilingual Hindi/English agent, TTS advisories, PDF in both languages |

### 1.3 Key Constraints (Non-Negotiable)

These constraints come directly from the build spec §0.1 and must be treated as product-level requirements:

1. **No invented values.** Every coefficient, price, threshold, or tariff must come from config or a cited source.
2. **Missing data = `unavailable`**, never `0` and never a national default.
3. **The LLM never computes numbers.** All numbers come from deterministic functions; the agent only explains tool outputs.
4. **Every number carries provenance** — source, date, class badge, assumption IDs.
5. **Ranges, not points** — for cool-roof impact, generation, payback, and forecasts.
6. **Local-first.** The entire prototype runs with `make dev` on a laptop (no AWS credentials required).
7. **No Kubernetes.** Serverless (Lambda, Step Functions) on AWS; `docker compose` locally.
8. **Wording rules** — LST is "surface temperature at a late-morning satellite pass"; drivers are "associated with"; biodiversity/soil outputs are "indicator"; forecasts are "forecast signal".

---

## 2. Users and Their Needs

| User | Needs | Key Modules |
|---|---|---|
| **Municipal Planner** | Ranked wards and roofs, costs, people protected, action list, recommendations, heat-dome forecasts, advisory approval, fire incident logging | M9, M10, M14, M15, M17, M38, M43 |
| **Homeowner / RWA** | Roof → system size, subsidy, payback range, checklist, PDF, bilingual agent guidance | M25–M32, M33+34, M35+36 |
| **Public** | Plain-language heat advisories (text + audio), fire alerts, in-app alert banner | M18+19, M22, M37, M38 |
| **Health / Emergency / Utility Officer** | Readiness prompts (hospital, electricity), fire alerts, forecast heat risk | M20+21, M22, M43 |
| **Environment / Forest Officer** | Protected-area fire and habitat-pressure warnings, degradation indicators | M22, M23, M24 |

---

## 3. Core Features (Module-by-Module)

### Phase 1A — Heat-to-Priority Pipeline

| Module | Feature | Description |
|---|---|---|
| **M1+2** | Location Input & Boundary | Resolve name/click/address/polygon → `LocationRef` with ward, city, state, DISCOM, geometry |
| **M3+4** | Landsat Acquisition & Preprocessing | STAC search, windowed COG reads, QA masking, cloud filtering, UTM reprojection |
| **M5** | Land Surface Temperature | USGS L2 ST product → median, p90, n_obs, IQR, per-year medians, hot_flag per scene |
| **M6** | Heat / Heat-Island Analysis | ΔLST vs rural reference, zonal stats per ward, hotspot detection (Gi*/percentile), persistence, NDVI/NDBI/NDWI/BSI |
| **M7** | Building Footprints | Ingest, repair, deduplicate, assign to wards, compute aggregates |
| **M8** | Population Exposure | WorldPop + building-level allocation, scaling, exposed population computation |
| **M8.5** | Ward Context Builder | Central merge of all features → provenance-tagged `ward_context` and `roof_context` |
| **M9** | Ward Priority Score | Configurable weighted scoring (heat, persistence, exposure, green deficit, roof opportunity) with sensitivity analysis |
| **M10** | Roof Prioritisation | Per-building scoring by benefit-per-rupee (local heat, pop, area, cost) |
| **M11+12+13** | Cool-Roof Impact, Cost, People Protected | Scenario triples (low/base/high), neighbourhood LST effect, indoor cooling, budget knapsack |
| **M14** | Municipal Action Ranking | Ward → building ranked action list with budget constraint and CSV export |

### Phase 1B — SuryaCheck

| Module | Feature | Description |
|---|---|---|
| **M25** | Solar Resource | PVGIS → fallback NASA POWER + pvlib → cached cell → unavailable; scenario losses |
| **M26** | Roof Suitability | Area computation, usable fraction, suitability flag, user questions |
| **M27+28** | System Size & Generation | Area-/load-/cap-limited sizing, degradation, monthly yields |
| **M29** | PM Surya Ghar Subsidy | Policy-as-data (DynamoDB), residential + GHS/RWA tiers, state top-up, staleness |
| **M30+31** | Net Metering & Payback | Tariff slabs, net metering vs net billing simulation, payback range with status codes |
| **M32** | SuryaCheck Orchestrator | Chains M1–M31, returns `complete | partial` with missing/next questions |

### Phase 1–2 — Agent, PDF, UI, Platform

| Module | Feature | Description |
|---|---|---|
| **M33+34** | Strands Agent (Hindi/English) | Bedrock-backed agent with typed tools, grounding check, language detection, session management |
| **M35+36** | Checklist & PDF | Jinja2 → HTML → WeasyPrint (Noto Devanagari), state/DISCOM-specific checklist, presigned URL |
| **M37** | Alerts & Notifications | Multi-producer alert hub (SNS), staff/public audiences, approval workflow, rate limiting, subscriptions |
| **M38** | Dashboard / Map | React + Vite + MapLibre + PMTiles, 11 screens (city picker, heat map, ward ranking, ward panel, roof list/detail, SuryaCheck, agent chat, alerts/forecast, PDF download, planner console) |
| **M39** | Backend API | FastAPI + pydantic v2 → OpenAPI, one router per domain, Mangum for Lambda |
| **M40** | Storage | S3 (raw/curated/tiles/models/rules/audio/exports), DynamoDB (9+ tables), dataset registry |
| **M41** | Auth | Anonymous sessions (Phase 1) → Cognito (Phase 2), 4 roles: anon/viewer/planner/admin |
| **M42** | Monitoring & Evaluation | CloudWatch metrics/alarms, CI gates, policy freshness, structured JSON logs |

### Phase 2 — Heat Intelligence

| Module | Feature | Description |
|---|---|---|
| **M15** | Heat-Type Classification + Authority Brief | Precedence-ordered rule classification (6 types), confidence scoring, per-ward authority brief from templates |
| **M16** | Heat Tracing (Driver Attribution) | OLS + GBM/SHAP, spatial CV, ward-level contribution (°C, direction, CI), always "associated with" |
| **M17** | Recommendation Engine | Versioned rules + evidence + cooling_options.json, 10 rule types (R-CR-01 through R-DG-01), tier ranking |
| **M18+19** | Public Awareness + TTS | Template-based EN/HI advisories, LLM tone rewrite with grounding check, approval workflow, Deepgram EN / Polly HI |
| **M20+21** | Hospital / Emergency & Electricity Readiness | Facility counting/placement, readiness prompts (HOSP-01/02, EXAM-01, COOL-01, ELEC-01), Phase 3 electricity forecast |

### Phase 2–3 — Hazards & Environment

| Module | Feature | Description |
|---|---|---|
| **M22** | Fire Detection & Alerts | Satellite (FIRMS VIIRS/MODIS) — poll, normalise, dedupe, classify by land cover; **Incident path** — staff report + confirm + optional fire-service feed; heat-linked fire risk advisory (R-FR-01) |
| **M23** | Biodiversity: Habitat Pressure Index | Per protected area — 4 indicators (fire, tree loss, NDVI trend, LST trend) → weighted index → low/moderate/high; PA fire/pressure-rise alerts; optional GBIF context |
| **M24** | Land / Soil Degradation Tracking | Multi-year NDVI/BSI/LST trend (Mann–Kendall + Sen's slope), rainfall-adjusted if CHIRPS available, Land Degradation Signal (none/weak/moderate/strong), transition alerts |
| **M43** | Heat-Dome / Extreme-Heat Forecast | Daily NWP ensemble — Tmax anomaly + Z500 ridge criteria → consecutive-day events → exceedance probability → risk level (none/watch/elevated/high); hindcast validation; triggers M17 and M20+21 |

---

## 4. Physical Caveats (Must Appear in UI and PDF)

These caveats **must be prominently displayed** in every user-facing surface:

- Landsat 8/9 thermal data is acquired **late morning**, native resolution ~100 m resampled to 30 m. LST ≠ air temperature, heat index, or night heat.
- Individual-roof LST **cannot be resolved**. Roof ranking uses neighbourhood heat + area + people + cost.
- **LST** = surface skin temperature at satellite pass.
- **Air temperature / heat index** = from stations or reanalysis, never Landsat.
- **Surface UHI** = LST − rural reference.
- **Exposure** = hazard × people (derived).
- Cool-roof coefficients and cost are **placeholders (ranges)** until calibrated by a 10–20 roof pilot.
- Forecast and environment outputs are **indicators or signals**, not official warnings or diagnoses.

---

## 5. Out of Scope

The following are explicitly **not part of this build**:

| Item | Reason |
|---|---|
| **Kubernetes / EKS** | Excluded by architecture rule (§0.1 rule 7) |
| **Glue, EMR, Kinesis, Redshift, OpenSearch** | Explicitly not used (§7) |
| **Air temperature from Landsat** | LST ≠ air temperature; air temp comes from stations/reanalysis only |
| **Individual-roof LST** | Native 100 m resolution prevents this; neighbourhood heat is used instead |
| **Biodiversity loss claims** | Module M23 is an "indicator" — never claims species or biodiversity loss |
| **Medical or legal advice** | Agent explicitly refuses these |
| **Application submission** | Agent never submits; always points to pmsuryaghar.gov.in |
| **Aadhaar, bank details, or document collection** | Privacy constraint; only name/address with consent |
| **Real-time or night-time heat** | Landsat is late-morning, episodic satellite; not real-time or nocturnal |
| **Official weather warnings** | System relays official IMD warnings; M43 is a "forecast signal", not an official warning |
| **Demand forecasting without utility data** | Phase 3, data-gated; only runs if `electricity_mode=forecast` and data exists |
| **Roof-type classification via CNN** | Phase 3, optional, data-gated |
| **Aurora/PostGIS** | Only if spatial SQL outgrows DuckDB (Phase 3) |
| **SMS alerts** | Requires sender registration [NV]; disabled until registration is complete |
| **National-default tariffs** | Tariffs are per state/DISCOM; no national default exists |
| **Automated approval of public advisories** | Always requires planner/admin approval (configurable two-person rule) |

---

## 6. Data Sources

The system relies on **21 data sources (D1–D21)** as defined in §3 of the build spec:

| ID | Dataset | Use |
|---|---|---|
| D1 | Landsat C2 L2 (L8/9) — ST_B10, ST_QA, QA_PIXEL, SR_B* | LST, NDVI/NDBI/NDWI/BSI |
| D2 | Ward boundaries | Analysis unit |
| D3 | Building footprints (Google Open Buildings / Overture / MS) | Roof area, density |
| D4 | WorldPop (+ Census 2011 check) | Population |
| D5 | Copernicus DEM GLO-30 | Terrain |
| D6 | ESA WorldCover | Land cover, reference mask, fire classing |
| D7 | PVGIS / NASA POWER | PV yield |
| D8 | ERA5 / IMD warnings | Context, official warnings |
| D9 | OSM hospitals, schools | Infrastructure |
| D10 | NASA FIRMS (VIIRS 375 m, MODIS 1 km) | Active fire (NRT) |
| D11 | WDPA (fallback: OSM `boundary=protected_area`) | Protected areas |
| D12 | SoilGrids | SOC, texture |
| D13 | PM Surya Ghar policy | Subsidy |
| D14 | DISCOM tariff / net metering | Savings |
| D15 | Utility load data | Demand forecast (Phase 3, data-gated) |
| D16 | NWP forecast (Open-Meteo / GFS-GEFS) — daily Tmax, Z500 | Heat-dome forecast (M43) |
| D17 | Climatology for Tmax and Z500 (ERA5 via Open-Meteo / CDS) | M43 anomalies |
| D18 | Hansen Global Forest Change (tree-cover loss) | M23 habitat pressure |
| D19 | CHIRPS rainfall | M24 rainfall-adjusted trends |
| D20 | GBIF occurrences (optional) | M23 species-recorded context |
| D21 | Fire-service incident feed (optional) | M22 urban/structure fires |

---

## 7. Success Criteria

| Criterion | Metric |
|---|---|
| Ward ranking reproducibility | Same config + data → identical ward list (hash check) |
| SuryaCheck accuracy | Golden JSON match for 3 locations; 3 kW → ₹78,000 subsidy; payback fixture = 2.0 yr |
| Agent grounding | 100% grounding pass rate across 30-turn golden suite (EN + HI) |
| PDF fidelity | Extracted text = source text (EN + HI); every number traces to assessment |
| Heat-dome hindcast | Detects planted event in fixture with expected first_day |
| Fire detection | Replay 1 month — report precision/recall; idempotent poll; latency metric |
| Degradation signal | Synthetic series (up/down/flat/noisy) → expected classes |
| Habitat pressure | Monotonic index; inside/edge/outside tests pass |
| Wording compliance | Denylist tests pass (no "caused by", "loss", "diagnosis", "official warning" misuse) |
| Local dev | `make dev` serves `/health` and full demo without AWS credentials |

---

## 8. Phasing Summary

| Phase | Scope | Key Deliverable |
|---|---|---|
| **Phase 1** | Heat pipeline (M1–M14) + SuryaCheck (M25–M36) + Agent MVP + UI MVP + Platform | Ranked wards, roof list, solar assessment, PDF, bilingual agent, basic dashboard |
| **Phase 2** | Heat intelligence (M15–M21) + Alerts (M37) + Cognito | Heat types, drivers, recommendations, advisories with TTS, readiness prompts |
| **Phase 2–3** | Hazards (M22, M43) + Environment (M23, M24) | Fire detection + incidents, heat-dome forecast, habitat pressure, degradation tracking |
| **Phase 3** | Data-gated optionals (M20+21 forecast mode, M15 GMM, roof-type CNN, Aurora) | Only if data, licences, or keys are provided |

---

## 9. Glossary

| Term | Definition |
|---|---|
| **LST** | Land Surface Temperature — surface skin temperature at the satellite pass |
| **ΔLST** | LST minus the rural reference median — surface Urban Heat Island proxy |
| **Ward Context** | The provenance-tagged data record for a ward, built by M8.5 |
| **Roof Context** | Per-building data record with geometry, local heat, population, solar, intervention data |
| **SuryaCheck** | The rooftop-solar assessment pipeline (M25–M32) |
| **PM Surya Ghar** | Government of India rooftop solar subsidy scheme |
| **DISCOM** | Distribution Company (electricity) |
| **FIRMS** | Fire Information for Resource Management System (NASA) |
| **HPI** | Habitat Pressure Index (M23) |
| **NWP** | Numerical Weather Prediction |
| **Strands** | AWS Strands Agents SDK for the AI agent |
| **Ward** | Administrative subdivision of a city (or H3/grid cell fallback) |
| **Value Envelope** | The JSON wrapper around every data value carrying provenance metadata |
| **Evidence Tag** | `[V]` verified, `[R]` recalled, `[NV]` needs verification, `[ASSUME]` modelling assumption |
