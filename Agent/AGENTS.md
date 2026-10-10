# AGENTS — Coding Instructions for AI Agents

> **Version:** 1.0 — Derived from [CoolRoof_Build_Spec_v0.3.md](CoolRoof_Build_Spec_v0.3.md)
> **Date:** 2026-10-10

---

## 1. Non-Negotiable Rules

These rules are **absolute**. Violating any of them makes the build invalid.

### 1.1 No Invented Values
- **NEVER** invent a coefficient, price, tariff, subsidy figure, threshold, or dataset field.
- Every assumption lives in `config/params.default.yaml` as a **parameter ID** (P-*) with status `[ASSUME]`, `[NV]`, or `[V]`.
- If a value is not in config, in a seed policy file, or in a verified source — **do not create it**. Instead, mark it `unavailable` and add an entry to `docs/GAPS.md`.

### 1.2 Missing Data Is `unavailable`, Never `0`
- If a data source is missing, the value is `"class": "unavailable"`.
- Never substitute `0`, `null` disguised as zero, or a "national default" for missing data.
- Follow the missing-data rules table in §10 of the build spec exactly.

### 1.3 The LLM Never Computes Numbers
- All numbers come from **deterministic functions** in the pipeline/services.
- The Strands agent (M33+34) **explains** tool outputs only.
- The agent template uses `{{tool.field}}` placeholders rendered deterministically.
- The grounding check (M33+34) **extracts all numbers** (Latin/Devanagari digits, ₹/Rs, lakh/crore, Indian grouping) and verifies each against session tool outputs. On failure: regenerate once, then fall back to a template.

### 1.4 Every Number Carries Provenance
- Every value shown to a user must include: `source`, `date`, `class` badge, and `assumption IDs`.
- Use the Value Envelope (§4.1) for every Ward Context field.
- In the UI, every number has a class badge with source/date/resolution on hover.

### 1.5 Ranges, Not Points
- Cool-roof impact, generation, payback, and forecasts must use **scenario triples** (low/base/high).
- Never show a single-point estimate where the spec requires ranges.

### 1.6 Local-First
- The entire prototype must run with `make dev` on a laptop without AWS credentials.
- Every external dependency has a `local` and `aws` adapter selected by `RUNTIME=local|aws`.
- Never write code that requires AWS credentials to test locally.

### 1.7 No Kubernetes
- Use serverless (Lambda, Step Functions) on AWS.
- Use `docker compose` locally.
- Never introduce EKS, Kubernetes manifests, or Helm charts.

### 1.8 Wording Rules (Enforced by Tests)
These exact phrasings must be used. Tests will reject violations:

| Context | Correct wording | Forbidden wording |
|---|---|---|
| LST | "surface temperature at a late-morning satellite pass" | "air temperature", "real-time temperature" |
| Heat drivers | "associated with" | "caused by", "due to" |
| Biodiversity / soil outputs | "indicator" | "loss", "diagnosis" |
| Heat-dome forecast | "forecast signal" | "official warning", "prediction" |
| M43 public text | "forecast signal, not an official warning" | Omitting the disclaimer |
| M23 | "habitat pressure indicator, unverified — not a measured biodiversity loss" | "biodiversity loss" |
| M24 | "indicator, not diagnosis" | "diagnosis", "confirmed degradation" |

### 1.9 Stop and Report, Don't Fake
- If a step needs a credential, unverified source (`[NV]`), or external data not yet available:
  1. Build the adapter interface with a clearly labelled fixture.
  2. List the gap in `docs/GAPS.md`.
  3. **Never** fake the data or silently skip the step.

### 1.10 Each Module Ships with Tests
- Every module must have tests implementing its **Verify** bullets from the build spec.
- A module is "done" only when all its Verify tests pass.
- `make test` must be green at every stage boundary.

---

## 2. Code Style and Naming Conventions

### 2.1 Python (Backend)

| Rule | Convention |
|---|---|
| **Version** | Python 3.11 |
| **Formatter** | `ruff format` |
| **Linter** | `ruff check` with default rules |
| **Type checker** | `mypy --strict` |
| **Naming** | `snake_case` for functions, variables, modules; `PascalCase` for classes; `UPPER_SNAKE` for constants |
| **Modules** | One file per module, named `m<number>_<short_name>.py` (e.g., `m05_lst.py`, `m085_context.py`) |
| **Imports** | Absolute imports from packages (e.g., `from packages.core.envelope import ValueEnvelope`) |
| **Docstrings** | Google style; required on every public function and class |
| **Type hints** | Required on every function signature; use `pydantic v2` for data models |
| **Error handling** | Custom exceptions from `packages/core/errors.py`; never bare `except:` |
| **Logging** | Structured JSON via `structlog`; include `request_id`/`run_id`; no PII |

### 2.2 TypeScript (Frontend)

| Rule | Convention |
|---|---|
| **Framework** | React with Vite |
| **Naming** | `PascalCase` for components; `camelCase` for functions/variables; `UPPER_SNAKE` for constants |
| **Components** | Functional components with hooks; no class components |
| **State** | React Query for server state; local state with `useState`/`useReducer` |
| **i18n** | i18next with `en.json` and `hi.json`; all user-facing strings through translation keys |
| **Styling** | CSS Modules or styled-components; colour-blind-safe palette |
| **Tests** | Playwright for E2E |

### 2.3 File Organisation

- Backend: `packages/<domain>/<module>.py`
- Frontend: `frontend/src/{components,pages,hooks,lib,i18n}/`
- Tests: `tests/{unit,property,golden,fixtures}/`
- Infrastructure: `infra/stacks/`
- Config: `config/`
- Rules/templates: `rules/v<N>/`
- Seed data: `seed/policy/`
- Docs: `docs/`

### 2.4 Git

- Commit messages: `<stage>/<module>: <description>` (e.g., `stage1/m05: implement LST computation`)
- One commit per logical change
- No large binary files (use fixtures directory, gitignore `data/`)

---

## 3. Libraries and Patterns

### 3.1 Required Libraries

**Backend (Python):**
```
# Geo
rasterio, GDAL, pystac-client, odc-stac, geopandas, shapely>=2, exactextract, duckdb, h3

# Stats/ML
numpy, xarray, scikit-learn, xgboost, shap, statsmodels, pymannkendall, pvlib

# API
fastapi, pydantic>=2, mangum, uvicorn

# Agent
strands-agents  # AWS Strands Agents SDK

# PDF
jinja2, weasyprint

# Infra
aws-cdk-lib, constructs

# Data
boto3, sqlite3 (stdlib), polars/pandas

# Utils
structlog, python-dotenv, apscheduler, httpx

# Testing
pytest, hypothesis, playwright
```

**Frontend (TypeScript):**
```
react, react-dom, vite, maplibre-gl, pmtiles, @tanstack/react-query, i18next, react-i18next
playwright (dev)
```

### 3.2 Architectural Patterns

#### Adapter Pattern (Local-First)
Every external dependency is behind an interface. The `RUNTIME` env var selects the implementation:

```python
# packages/adapters/blobstore.py
from abc import ABC, abstractmethod

class BlobStore(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...
    @abstractmethod
    def get(self, key: str) -> bytes: ...

class LocalBlobStore(BlobStore):
    """Reads/writes to ./data/ folder"""
    ...

class S3BlobStore(BlobStore):
    """Uses boto3 S3 client"""
    ...

def get_blobstore() -> BlobStore:
    if os.environ.get("RUNTIME") == "aws":
        return S3BlobStore()
    return LocalBlobStore()
```

#### Value Envelope Pattern
Every data value is wrapped with provenance:

```python
# packages/core/envelope.py
from pydantic import BaseModel
from typing import Optional
from enum import Enum

class ValueClass(str, Enum):
    MEASURED = "measured"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    POLICY = "policy"
    USER = "user"
    UNAVAILABLE = "unavailable"
    STALE = "stale"

class ValueEnvelope(BaseModel):
    value: Optional[float | str | int] = None
    cls: ValueClass
    source: str
    observed: Optional[str] = None
    processed: str
    resolution_m: Optional[int] = None
    confidence: Optional[float] = None
    stale_after: Optional[str] = None
```

#### Pipeline Pattern
Batch modules form a Step Functions pipeline (Python orchestrator locally). Each module is a pure function:

```python
# Input → Processing → Output (with provenance)
def run(inputs: ModuleInput, params: Params) -> ModuleOutput:
    ...
```

#### Policy-as-Data Pattern
Subsidies, tariffs, checklists are **data records** in the DocStore, not hardcoded:

```python
# Never hardcode: S(3) = 78000
# Instead: load from policy record and compute
policy = docstore.get("policy#subsidy#ALL#ALL", effective_date)
subsidy = compute_subsidy(kw=3, policy=policy)
```

#### Grounding Check Pattern
The agent never outputs a number that isn't in tool outputs:

```python
# packages/core/grounding.py
def extract_numbers(text: str) -> set[str]:
    """Extract all number representations (Latin, Devanagari, ₹, lakh/crore, etc.)"""
    ...

def check_grounding(response: str, tool_outputs: dict) -> GroundingResult:
    """Every number in response must appear in tool_outputs"""
    ...
```

### 3.3 API Patterns

- **One router per domain** — never mix concerns
- **pydantic v2 models** for request/response — auto-generates OpenAPI
- **Standard response envelope** — `{data, meta}` or `{error}`
- **Idempotency** — `input_hash` for repeatable calls; `POST /analysis/heat` returns 202
- **Error codes** — use exactly the codes from §4.5 (400, 401, 403, 404, 409, 422, 424, 429, 502, 504)

### 3.4 Testing Patterns

| Type | Location | Purpose |
|---|---|---|
| **Unit** | `tests/unit/` | Per-module logic, Verify bullets |
| **Property** | `tests/property/` | Hypothesis-based (monotonicity, mass conservation, etc.) |
| **Golden** | `tests/golden/` | Frozen input → expected output (SuryaCheck 3 locations, agent 30 turns) |
| **Fixtures** | `tests/fixtures/mini_city/` | 12-ward synthetic city for offline testing |
| **Wording** | CI gate | Denylist test for forbidden phrases |
| **Schema** | CI gate | JSON-schema validation of all context records |
| **Contract** | CI gate | API response matches OpenAPI spec |

---

## 4. Things the Agent Must NEVER Change

These are **immutable architectural decisions** from the build spec. Do not modify, override, or work around them.

### 4.1 Architecture
- ❌ Do NOT introduce Kubernetes, EKS, Helm, or container orchestration beyond `docker compose`
- ❌ Do NOT use Glue, EMR, Kinesis, Redshift, or OpenSearch
- ❌ Do NOT remove the local-first adapter pattern
- ❌ Do NOT make any module require AWS credentials to run locally
- ❌ Do NOT use single-channel or split-window methods for LST (USGS L2 ST product only)
- ❌ Do NOT use MODIS LST as the primary source (cross-check only)

### 4.2 Data Integrity
- ❌ Do NOT hardcode any subsidy figure, tariff, cost, or threshold in application code (policy-as-data only)
- ❌ Do NOT set missing values to `0` or substitute national defaults
- ❌ Do NOT allow the LLM to compute, invent, or modify any number
- ❌ Do NOT remove provenance tracking from any data value
- ❌ Do NOT remove the Value Envelope from Ward Context fields
- ❌ Do NOT let any module other than M8.5 write whole ward context versions
- ❌ Do NOT auto-confirm fire incidents (requires second staff confirmation)
- ❌ Do NOT auto-approve public advisories or alerts (requires planner/admin)

### 4.3 Verified Facts
These are verified ([V]) and must not be modified:

| ID | Fact | Status |
|---|---|---|
| F1 | PM Surya Ghar residential subsidy: ₹30,000/kW up to 2 kW + ₹18,000/kW for 2–3 kW. Capped at ₹78,000 above 3 kW | [V] |
| F2 | Size by monthly use: 0–150 units → 1–2 kW; 150–300 → 2–3 kW; >300 → >3 kW | [V] |
| F3 | GHS/RWA: ₹18,000/kW for common facilities incl. EV, ≤500 kW at 3 kW/house | [V] |
| F4 | Applications at pmsuryaghar.gov.in | [V] |
| F5 | Subsidy released after DISCOM commissioning + bank details, "within 30 days" | [V, secondary] |
| F8 | Landsat C2 L1/L2 in `s3://usgs-landsat`, Requester Pays, us-west-2, STAC; SNS `public-c2-notify-v2` | [V] |
| F9 | Landsat has no use restrictions; attribution requested | [V] |
| F10 | Deepgram Aura-2 TTS covers EN but **not Hindi** (Hindi is STT only) | [V] |

### 4.4 Module Boundaries
- ❌ Do NOT merge modules that the spec defines separately
- ❌ Do NOT add admin/planner write tools to the agent's tool registry (M33+34)
- ❌ Do NOT let M22 satellite fire candidates auto-confirm as structure fires
- ❌ Do NOT let M43 forecast-based advisories default to public audience (staff only; public needs explicit approval)
- ❌ Do NOT let M23 claim species or biodiversity loss
- ❌ Do NOT let M24 claim "diagnosis" — it produces "indicators" only
- ❌ Do NOT let M15 ML clustering overwrite rule-based labels

### 4.5 API Contract
- ❌ Do NOT change the response envelope format (`{data, meta}` or `{error}`)
- ❌ Do NOT change the error code semantics (especially 424 for stale/missing policy)
- ❌ Do NOT remove the `request_id` from responses
- ❌ Do NOT remove `context_version` or `policy_version` from meta

### 4.6 Security and Privacy
- ❌ Do NOT collect Aadhaar numbers, bank details, or identity documents
- ❌ Do NOT store PII outside sessions, hashed subscriptions, and PDFs
- ❌ Do NOT remove the consent notice before collecting name/address
- ❌ Do NOT extend PDF presigned URL validity beyond 24h or lifecycle beyond 7 days
- ❌ Do NOT log PII in structured logs

---

## 5. Configuration Management

### 5.1 Parameters (`config/params.default.yaml`)

Every P-* parameter must exist in this file with:
- `value` — the value or `null` if unknown
- `status` — `[ASSUME]`, `[NV]`, or `[V]`
- `source` — where the value comes from
- `module` — which module(s) use it

Never hardcode P-* values in code. Always load from the params registry.

### 5.2 City Config (`config/cities/<city>.yaml`)

Per-city configuration includes:
- `bbox` — bounding box
- `season` — hot season window (default Mar 1 – Jun 15)
- `utm_epsg` — UTM zone EPSG code
- `discom_map` — city → state → DISCOM mapping
- `weight_profile` — priority weight profile (or AHP results)

### 5.3 Rules (`rules/v<N>/`)

All rule files are **immutable S3-versioned**:
- `rules.json` — recommendation rules
- `evidence.json` — evidence registry
- `cooling_options.json` — economical cooling catalog
- `heat_type_briefs.json` — authority briefs per heat type
- `advice.json` — advisory text whitelist
- `glossary.json` — Hindi/English glossary
- `templates/{en,hi}/*.j2` — advisory templates

CI rejects any rule with an empty `evidence_ref`.

---

## 6. Error Handling

### 6.1 Error Hierarchy

```python
class CoolRoofError(Exception): ...

class ValidationError(CoolRoofError): ...         # 400
class AuthError(CoolRoofError): ...               # 401/403
class NotFoundError(CoolRoofError): ...           # 404
class ConflictError(CoolRoofError): ...           # 409
class IncompleteError(CoolRoofError): ...         # 422
class PolicyError(CoolRoofError): ...             # 424
class ThrottledError(CoolRoofError): ...          # 429
class UpstreamError(CoolRoofError): ...           # 502
class TimeoutError(CoolRoofError): ...            # 504
```

### 6.2 Fallback Chain

When a data source fails, follow the fallback chain from the spec:
1. Use the configured fallback source (e.g., PVGIS → NASA POWER + pvlib → cache)
2. If all sources fail → `unavailable`
3. **Never** invent data, use a default, or silently skip

---

## 7. Checklist Before Marking a Module Done

- [ ] All Verify bullets from the build spec are implemented as tests
- [ ] All tests pass (`make test`)
- [ ] Type checking passes (`mypy --strict`)
- [ ] Linting passes (`ruff check`)
- [ ] No hardcoded values (all from config/policy)
- [ ] Missing data handled as `unavailable`, not `0`
- [ ] Provenance (Value Envelope) on all output values
- [ ] Wording rules followed (check denylist)
- [ ] Local adapter works without AWS credentials
- [ ] Entry added to `docs/DEMO.md`
- [ ] Gaps listed in `docs/GAPS.md` (if any [NV] items)
