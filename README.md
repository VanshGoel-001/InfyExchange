# InfyExchange

InfyExchange is a marketplace for the Infosys Mysore trainee community. Members can list items to sell, rent, lend, or give away; post requests; and contact each other after an offer is accepted. Administrators can moderate listings and manage users.

## Architecture

The frontend and backend are deployed separately.

| Component | Stack | Hosting |
| --- | --- | --- |
| Web app | React, Vite | Cloudflare Pages |
| API | FastAPI, SQLAlchemy, Alembic | Google Cloud Run |
| Database | PostgreSQL | Neon |
| Images | Cloudinary | Cloudinary |

Cloud Run serves the API over HTTPS. Neon manages PostgreSQL; Cloudinary stores listing images. See [the security docs](docs/security/) for architecture and operational details.

## Requirements

- Node.js 20 or later
- Python 3.12
- Docker with Compose

## Run Locally

Start PostgreSQL from `backend/`:

```powershell
cd backend
docker compose up -d
```

In a second terminal, configure and start the API:

```powershell
cd backend
Copy-Item .env.example .env
# Set SECRET_KEY and the CLOUDINARY_* values in .env.
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a third terminal, start the frontend from the repository root:

```powershell
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite forwards `/api` requests to the local API. The API applies pending database migrations at startup and exposes `/health`; interactive API docs are available at `/docs` in development.

## Configuration

Use [backend/.env.example](backend/.env.example) as the local backend template. Set `SECRET_KEY`, `DATABASE_URL`, and the three `CLOUDINARY_*` values. The local Compose database listens only on `127.0.0.1:5432`.

In production, store `NEON_DATABASE_URL` (pooled) and `NEON_DATABASE_URL_UNPOOLED` (direct), `SECRET_KEY`, and the three `CLOUDINARY_*` values in Google Secret Manager. Both Neon URLs must use the `postgresql+psycopg://` scheme and TLS. The runtime uses the pooled URL; Alembic migrations use the direct URL. Set the GitHub Actions variable `CORS_ORIGINS` to the exact Cloudflare Pages origin.

Set `VITE_API_BASE_URL` in the Cloudflare Pages project settings to the API origin plus `/api`, for example `https://api.example.com/api`. Vite embeds this value during the build, so changing it requires a new deployment. Local development uses Vite's proxy and does not need this setting.

## Deploy

The `deploy/neon-cloudrun-cloudflare-pages` branch runs CI before sequential Cloud Run and Cloudflare Pages deployments. The release image is scanned and deployed by digest. Configure Workload Identity Federation and the `neon-staging` GitHub environment; grant the deploy account least-privilege Artifact Registry and Cloud Run permissions, and grant the runtime account access to the six secrets listed above. Configure these repository or environment values:

| Name | Type | Purpose |
| --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Variable | Cloudflare account identifier |
| `CLOUDFLARE_PAGES_PROJECT` | Variable | Pages project name |
| `VITE_API_BASE_URL` | Variable | Cloud Run service URL ending in `/api` |
| `CLOUDFLARE_API_TOKEN` | Secret | Token with permission to deploy Pages |
| `GCP_PROJECT_ID` | Variable | Google Cloud project ID |
| `GCP_REGION` | Variable | Cloud Run region |
| `CLOUD_RUN_SERVICE` | Variable | Cloud Run service name |
| `ARTIFACT_REGISTRY_REPOSITORY` | Variable | Pre-created Docker repository in Artifact Registry |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Variable | Full Workload Identity Provider resource name |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | Variable | GitHub deployment service account email |
| `CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT` | Variable | Cloud Run runtime service account email |
| `CORS_ORIGINS` | Variable | Exact Pages origin allowed by the API |

Create the Cloud Run service and Artifact Registry repository once. Set `VITE_API_BASE_URL` to the service URL plus `/api`. Configure reviewer approval and branch restrictions on `neon-staging`; see [the operations runbook](docs/security/SECURITY_RUNBOOK.md).
## Verify

Run the frontend checks from the repository root:

```powershell
npm ci
npm audit --audit-level=high
npm run build
```

Run the backend checks from `backend/`:

```powershell
python -m pytest -q
python -m bandit -r app -q
python -m pip_audit -r requirements.txt --progress-spinner off
```

GitHub Actions runs tests, SAST, dependency and secret scans, configuration checks, and container vulnerability scanning. The controls and remaining administrator actions are listed in [the DevSecOps pipeline checklist](docs/security/DEVSECOPS_PIPELINE.md). For a live API security scan, see [the ZAP scan script](scripts/security/zap-api-scan.ps1).

## Operations

- Configure Neon backups and point-in-time recovery for the selected plan; periodically verify restore procedures.
- JWTs are stored in browser `localStorage`.
- Rate limits are held in API process memory; multiple API instances would need a shared store such as Redis.
- Profile editing, password changes, and account deletion are not currently supported by the API.

## Project Structure

```text
src/                  React application
backend/app/           FastAPI routes, models, schemas, and services
backend/alembic/       Database migrations
backend/tests/         Backend tests
backend/docker-compose.yml  Local PostgreSQL service
docs/security/         Architecture and operational documentation
scripts/security/      Security scan and OpenAPI tools
```
