# CoolRoof infrastructure (AWS CDK, Python)

Six stacks. `cdk deploy --all` creates them in dependency order.

| Stack | Creates |
|---|---|
| `CoolRoofDataStack` | S3 bucket, 12 DynamoDB tables (`coolroof-*`) |
| `CoolRoofAlertsStack` | SNS topics `coolroof-<city>-staff` / `-public`, Secrets Manager secret `coolroof/app` |
| `CoolRoofAuthStack` | Cognito user pool with `planner` and `admin` groups, web client |
| `CoolRoofApiStack` | Lambda container (FastAPI via Mangum) behind API Gateway; grants for S3, DynamoDB, the secret, SNS, Polly, Bedrock |
| `CoolRoofJobsStack` | Same image, handler `packages.api.scheduled.handler`; EventBridge rules for fire poll (P-FIRE-POLL), heat-dome forecast 01:30 UTC, staleness flip 02:00 UTC |
| `CoolRoofMonitoringStack` | CloudWatch alarms (API errors, 5XX, job errors) and a monthly AWS Budget |

Not in CDK: **frontend hosting.** Amplify needs a GitHub connection that is made in the console, or use Vercel.
Run the Next.js app anywhere with `BACKEND_URL=<ApiUrl>`; it proxies `/api/*` to that URL.

## Before the first deploy

1. AWS CLI configured (`aws configure` or `aws configure sso`) and Docker running (the Lambda image is built locally).
2. In the Bedrock console, enable access to the model you will use in your region.
3. A region: default `ap-south-1`; override with `CDK_DEFAULT_REGION`.

## Deploy

```powershell
cd infra
python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt
npm install
npx cdk bootstrap
npx cdk deploy --all `
  -c bedrock_model_id=<model id or inference profile> `
  -c frontend_origin=https://<your frontend host> `
  -c ops_email=you@example.com
```

Context keys (all optional): `city` (default `mini_city`), `bedrock_model_id`, `frontend_origin` (CORS, default `*`),
`ops_email` (alarm, budget and staff-alert emails; confirm the subscription mails), `monthly_budget_usd` (default 50),
`data_sources=fixture|live` (default `fixture`; `live` switches Landsat, Open-Meteo, PVGIS/NASA POWER and FIRMS to the real services).

## After the deploy

* **Secret `coolroof/app`** (Secrets Manager console): `PLANNER_API_KEY` is generated for you. Set `ADMIN_API_KEY`
  (admin routes are disabled while it is empty), `DEEPGRAM_API_KEY` (English audio) and, for live fire data, `FIRMS_MAP_KEY`.
  The Lambdas read the secret on cold start, so redeploy or wait for new containers after editing it.
* **Cognito:** create users in the pool and add them to `planner` or `admin`. Send the ID token as `Authorization: Bearer ...`.
  API keys (`X-API-Key`) keep working.
* **Load the data** (writes S3 + DynamoDB):
  ```powershell
  cd ..\backend
  $env:RUNTIME="aws"; $env:S3_BUCKET="<DataBucket name>"; $env:AWS_REGION="<region>"
  uv run python -m scripts.run_pipeline --city mini_city
  ```
  The script reads the secret `coolroof/app`, so it needs the same AWS credentials.
* **Smoke test:** `GET <ApiUrl>/health`, `/wards`, then `/agent/chat`, an alert send, `/tts`, `/documents/application-pdf`.
  None of these AWS paths has run against a real account yet.

## Tests

`pytest` in this folder synthesises every stack offline (no account, no Docker build) and checks the wiring:
secret name, SNS topic names, Lambda environment, IAM actions, schedules, Cognito groups, alarms and budget.
