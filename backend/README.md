# CoolRoof backend

Python 3.12 backend for CoolRoof Planner + Heat Intelligence + SuryaCheck: batch
heat pipeline, request-time services, the bilingual agent and the FastAPI app.
The source of truth for behaviour is `../Agent/CoolRoof_Build_Spec_v0.3.md`.

## Quick start (Windows-native, no GDAL / GTK / make needed)

```powershell
cd backend
uv sync --all-extras          # creates .venv with Python 3.12
uv run poe seed               # load seed policy records into the local DocStore
uv run poe api                # http://localhost:8000/health
uv run poe test               # all tests (offline, mini-city fixture)
uv run poe ci                 # lint + strict type check + tests
```

Run `uv run poe` to list every task.

## Layout

| Path | Contents |
|---|---|
| `packages/core` | Shared contracts: value envelope, enums, errors, parameter registry, IDs, grounding, i18n, wording rules |
| `packages/adapters` | Interfaces with `local` and `aws` implementations, selected by `RUNTIME` |
| `packages/pipeline` | Batch modules (M1–M16, M23, M24, M43) |
| `packages/services` | Request-time and scheduled services (M17–M37) |
| `packages/agent` | Bilingual agent (M33+34) |
| `packages/api` | FastAPI app and one router per domain |
| `config/` | `params.default.yaml` (every P-* parameter) and per-city configs |
| `rules/v1/` | Versioned recommendation rules, evidence, templates |
| `seed/policy/` | Seed policy records (subsidy, synthetic test tariff, checklist) |
| `tests/` | `unit/`, `property/`, `golden/`, `fixtures/mini_city/` |
| `scripts/` | Fixture generator, seeding, pipeline runner |
