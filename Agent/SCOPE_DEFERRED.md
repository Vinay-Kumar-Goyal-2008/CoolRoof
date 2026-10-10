# SCOPE_DEFERRED — modules removed from the current build

> **UPDATE (2026-10-10): every module below has since been built** (M16, M18+19, M20+21, M22, M23, M24, M37, plus
> Cognito token verification, the alerts/advisory/incident/admin APIs and screens 9 and 11), with tests. See the README
> status tables and `docs/GAPS.md` §6–7 for what is still unverified. The text below is kept as the original decision record.

> **Decided:** 2026-10-10, by the project owner, to focus the hackathon build on one problem
> (urban heat → which roofs to cool, and rooftop-solar for households) and keep it working end to end.
> Judging criteria in mind: idea and impact, built on AWS, design and usability, a working execution, a 3-minute demo video.

The modules below are **deferred, not deleted**. The specs (`CoolRoof_Build_Spec_v0.3.md`, `SPEC.md`, `PRD.md`) and
their `TASKS.md` entries stay as the roadmap. No code is written for them in this build, and the UI,
API and agent show no screens, routes or tools for them.

## Deferred modules

| Module | What it does | Why deferred |
|---|---|---|
| **M16** Heat tracing (driver attribution, GBM + SHAP) | Which land features are associated with a ward's heat | Heavy ML; little value in a short demo |
| **M18+19** Public advisories + TTS (Deepgram EN / Polly HI) | Approved bilingual advisory text and audio | Separate workflow from the core story |
| **M37** Alerts and notifications (SNS) | Alert hub, subscriptions, approval gates | Depends on the producers above and below |
| **M20+21** Hospital / emergency and electricity readiness | Readiness prompts for health and utility officers | Different audience |
| **M22** Fire detection and alerts (FIRMS + incidents) | Satellite and structure-fire alerts | Different environmental problem |
| **M23** Biodiversity: Habitat Pressure Index | Protected-area pressure indicator | Different environmental problem |
| **M24** Land / soil degradation tracking | Multi-year NDVI/BSI/LST trend signal | Different environmental problem |

## Consequences for the rest of the build

* **Ward Context** keeps the full spec schema. Fields owned by deferred modules
  (`heat.top_drivers`, `heat.drivers_ref`, `environment.*_trend_slope`, `environment.degradation_signal`,
  `infrastructure.*`, `hazards.*`) are simply absent, i.e. `unavailable`, which the schema, API and UI already treat as normal.
* **M17 recommendations** run only the rules that do not depend on deferred modules.
  Not built: R-RD-01 (readiness), R-FR-01 (fire risk), R-DG-01 (degradation).
  Built (rule-based, with evidence): R-CR-01, R-SO-01, R-CP-01, R-GR-01, R-EC-01, plus R-HD-01 / R-EX-01 if M43 is built.
* **M43 heat-dome forecast** was *not* removed; it stays in scope but is lower priority than the core demo.
* **Agent tools:** only the MVP tools plus `get_roof_context`, `get_heat_analysis` (heat type only), `get_recommendations`
  and, with M43, `get_heatdome_forecast`. Not built: `get_readiness`, `get_alerts`, `get_advisory`,
  `get_habitat_pressure`, `get_degradation`.
* **API:** routers `fire`, `environment` and the advisory / TTS / readiness / alert-subscription endpoints are not built.
* **Dashboard:** screen 9 shows only the heat-dome panel (if M43 ships); screen 11 (planner console) is cut.
* **AWS:** SNS, EventBridge schedules for FIRMS, Polly and Cognito are not needed for the deferred work.
* **Parameters:** P-FIRE-*, P-PA-BUFFER, P-VEG-DROP, P-HPI-*, P-LOSS-ALERT, P-TREND-*, P-BUILT-NA, P-COVMIN,
  P-COVER, P-ALERT-RATE, P-DRIVER-* stay in `params.default.yaml` unused, so reinstating a module needs no config work.

## Bringing a module back

Each deferred module is self-contained in the spec: add its file under `packages/pipeline` or `packages/services`,
register its feature table in M8.5 (`FieldSpec`), add its router, and add its tests from the spec's Verify bullets.
