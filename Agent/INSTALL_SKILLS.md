# INSTALL_SKILLS — Agent Skills for the CoolRoof Build

> **Instructions for Claude Code:** Install every skill listed below, using **PowerShell**, from the **project root folder** (the folder that contains `AGENTS.md`, `SPEC.md`, `TASKS.md`). Skills come from https://skills.sh and are installed with the `skills` CLI via `npx`.

## Rules for you (Claude Code)

1. Work in PowerShell. Run each command on its own line. Do not use bash syntax, `&&` chaining, or backslash line continuations.
2. Run all commands from the project root. Confirm with `Get-Location` first.
3. Prerequisite check: run `node --version` (needs Node 18+) and `npx --version`. If Node is missing, stop and tell me. Do not try to install it silently.
4. Add `-a claude-code -y` to each command so it targets Claude Code and does not stop for prompts. If a command fails because a flag is not recognised, run `npx skills add --help`, adjust the flags, and continue. Do not drop the `--skill` selection.
5. Install **Part A (core)** first, then **Part B (extras)**. Skip nothing in A. Part B is also wanted, but if a B command fails, report it and continue.
6. If one command fails, do not abort the rest. Record the failure and keep going.
7. Do not install anything from the "Do NOT install" list.
8. When finished, run `npx skills list` and report a table of: skill name, installed (yes/no), and any errors.
9. Do not edit `AGENTS.md`, `SPEC.md`, `PRD.md`, `TASKS.md` or `README.md` as part of this task, unless I ask in a separate message.

## Part A — Core skills (required)

```powershell
npx skills add wshobson/agents --skill python-testing-patterns -a claude-code -y
npx skills add wshobson/agents --skill python-type-safety -a claude-code -y
npx skills add wshobson/agents --skill python-code-style -a claude-code -y
npx skills add wshobson/agents --skill python-project-structure -a claude-code -y
npx skills add wshobson/agents --skill python-error-handling -a claude-code -y
npx skills add wshobson/agents --skill python-configuration -a claude-code -y
npx skills add wshobson/agents --skill python-observability -a claude-code -y
npx skills add wshobson/agents --skill fastapi-templates -a claude-code -y
npx skills add wshobson/agents --skill api-design-principles --skill openapi-spec-generation -a claude-code -y
npx skills add wshobson/agents --skill uv-package-manager -a claude-code -y
npx skills add mattpocock/skills --skill tdd -a claude-code -y
npx skills add vercel-labs/agent-skills --skill vercel-react-best-practices --skill web-design-guidelines -a claude-code -y
npx skills add anthropics/skills --skill frontend-design --skill webapp-testing -a claude-code -y
npx skills add microsoft/playwright-cli -a claude-code -y
```

| Skill | Why it is needed in this project |
|---|---|
| python-testing-patterns | pytest, fixtures and mocking for the mini-city tests and "every module ships Verify tests" |
| python-type-safety | `mypy --strict`, type hints on every signature |
| python-code-style | ruff, naming, Google-style docstrings |
| python-project-structure | `packages/core`, `adapters`, `pipeline`, `services` layout |
| python-error-handling | `CoolRoofError` hierarchy and the 400 to 504 code mapping |
| python-configuration | params registry and the `RUNTIME=local\|aws` switch |
| python-observability | structlog JSON logs with request IDs and no PII |
| fastapi-templates | routers, pydantic v2, `{data, meta}` envelope, Mangum |
| api-design-principles, openapi-spec-generation | the 11 domain routers and contract tests against OpenAPI |
| uv-package-manager | uv with Python 3.12 |
| tdd | red-green loop for Verify-bullet tests |
| vercel-react-best-practices, web-design-guidelines | React/Vite quality, keyboard access, colour-blind-safe UI |
| frontend-design, webapp-testing | the 11 screens, planner console, SuryaCheck card, browser testing |
| playwright-cli | E2E happy path and unavailable-state tests |

## Part B — Extras (also install)

```powershell
# AWS deploy (Stage 7) — newer, low-install skills, so these may be less polished
npx skills add awslabs/agent-plugins --skill aws-lambda --skill aws-serverless-deployment --skill aws-step-functions --skill api-gateway -a claude-code -y

# Security, auth, privacy (Cognito roles, PII rules, secrets)
npx skills add wshobson/agents --skill secrets-management --skill auth-implementation-patterns --skill gdpr-data-handling -a claude-code -y

# Planning and design workflow
npx skills add mattpocock/skills --skill grill-with-docs --skill to-spec --skill domain-modeling -a claude-code -y

# Documenting the immutable architecture decisions
npx skills add wshobson/agents --skill architecture-decision-records -a claude-code -y

# Lets the agent search for further skills itself
npx skills add vercel-labs/skills --skill find-skills -a claude-code -y
```

## Do NOT install (conflicts with project rules)

- `k8s-*`, `helm-chart-scaffolding`, `istio-*`, `linkerd-patterns`, `service-mesh-*`: Kubernetes is banned (AGENTS.md section 4.1).
- `terraform-module-library`: infrastructure is AWS CDK (Python), not Terraform.
- `python-background-jobs`, `async-python-patterns`: not used. The scheduler is APScheduler locally and EventBridge on AWS.
- Anthropic `pdf` skill: it is built around reportlab/pypdf, and this project uses fpdf2 + uharfbuzz with PyMuPDF for text checks.

## Verification (do this last)

```powershell
npx skills list
```

Report any skill from Parts A and B that is missing. Then give me a short summary: how many installed, how many failed, and the exact error text for each failure.

## Important project context (for reference, do not act on it now)

These design decisions override what older text in `AGENTS.md`, `SPEC.md`, `TASKS.md` and `README.md` says. When using the installed skills, follow these:

| Old text in docs | Use instead |
|---|---|
| Python 3.11 | **Python 3.12**, managed with **uv** |
| GNU Make (`make dev`, `make test`, `make lint`) | **poethepoet** (`poe dev`, `poe test`, `poe lint` in `pyproject.toml`) plus **honcho** to run API and frontend together |
| GDAL as a system install | Not needed. rasterio 1.5.2 wheels bundle GDAL 3.12, and pyogrio (GeoPandas) bundles GDAL too |
| WeasyPrint (Jinja2 to HTML to PDF) | **fpdf2 + uharfbuzz** for layout and Hindi shaping, Jinja2 for text only, **PyMuPDF** to read PDF text back in tests |
| Windows font | Bundle **Noto Sans Devanagari** (open licence) |
| Docker for local dev | Not needed locally. Only needed to build the AWS Lambda container image for the rasterio functions (they exceed the 250 MB zip limit) |

Hindi PDF test rule: extracted text contains stray control characters at conjunct letters (for example `सब्सि\u0003डी`). The PDF test must compare text **after stripping control characters**, not raw equality.

Suggested follow-up task for me to request later: "Update AGENTS.md, SPEC.md, TASKS.md and README.md to reflect the table above."
