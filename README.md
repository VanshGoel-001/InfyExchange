# InfyExchange

InfyExchange is a marketplace for the Infosys Mysore trainee community. Members can list items to sell, rent, lend, or give away; post requests; and contact each other after an offer is accepted. Administrators can moderate listings and manage users.

## Architecture

The frontend and backend are deployed separately.

| Component | Stack | Hosting |
| --- | --- | --- |
| Web app | React, Vite | Cloudflare Pages |
| API | FastAPI, SQLAlchemy, Alembic | Oracle Cloud VM or another Linux host |
| Database | PostgreSQL 17 | Docker Compose, private network |
| Images | Cloudinary | Cloudinary |

The VM runs Caddy for HTTPS, Nginx as a private API proxy, the API, and PostgreSQL. Only Caddy publishes ports 80 and 443. See [the security docs](docs/security/) for architecture and operational details.

## Requirements

- Node.js 20 or later
- Python 3.12
- Docker with Compose

## Run Locally

Start PostgreSQL from `backend/`:

```powershell
cd backend
docker compose --profile dev up -d
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

Use [backend/.env.example](backend/.env.example) as the backend template. For local API runs, set `SECRET_KEY`, `DATABASE_URL`, and the three `CLOUDINARY_*` values.

Production Compose requires `SECRET_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `API_DOMAIN`, `CORS_ORIGINS`, and the three `CLOUDINARY_*` values. Compose builds the database URL from the `POSTGRES_*` settings. Use a real DNS name for `API_DOMAIN`, point it to the VM, and set `CORS_ORIGINS` to the exact Cloudflare Pages origin.

Set `VITE_API_BASE_URL` in the Cloudflare Pages project settings to the API origin plus `/api`, for example `https://api.example.com/api`. Vite embeds this value during the build, so changing it requires a new deployment. Local development uses Vite's proxy and does not need this setting.

## Deploy

On the VM, create `backend/.env` from the example, enter the production values, then run:

```bash
cd backend
docker compose --profile prod up -d --build
```

Caddy obtains and renews the TLS certificate for `API_DOMAIN`. Ports 80 and 443 must be reachable from the internet. PostgreSQL, the API, and Nginx are not published to the host.

Cloudflare Pages deployment runs from GitHub Actions after CI succeeds on a push to `main`. Configure these repository values:

| Name | Type | Purpose |
| --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Variable | Cloudflare account identifier |
| `CLOUDFLARE_PAGES_PROJECT` | Variable | Pages project name |
| `VITE_API_BASE_URL` | Variable | API URL ending in `/api` |
| `CLOUDFLARE_API_TOKEN` | Secret | Token with permission to deploy Pages |

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

GitHub Actions runs these checks and validates the Compose, Nginx, Caddy, and backup configurations. For a live API security scan, see [the ZAP scan script](scripts/security/zap-api-scan.ps1).

## Operations

- Create encrypted PostgreSQL backups with [the backup script](backend/scripts/backup-postgres.sh). Setup and restore instructions are in [the security runbook](docs/security/SECURITY_RUNBOOK.md).
- JWTs are stored in browser `localStorage`.
- Rate limits are held in API process memory; multiple API instances would need a shared store such as Redis.
- Profile editing, password changes, and account deletion are not currently supported by the API.

## Project Structure

```text
src/                  React application
backend/app/           FastAPI routes, models, schemas, and services
backend/alembic/       Database migrations
backend/tests/         Backend tests
backend/docker-compose.yml  Local and production services
docs/security/         Architecture and operational documentation
scripts/security/      Security scan and OpenAPI tools
```
