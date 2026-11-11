# InfyExchange

A campus marketplace for the Infosys Mysore trainee community: **buy, rent, lend and give away** items within campus, plus a "needs" board where trainees post what they are looking for and others offer items via interests. An accepted interest unlocks a contact exchange, and an admin control plane provides moderation, user management and an audit trail.

Two independently deployed applications:

| Layer | Tech | Deployed to |
|---|---|---|
| Frontend | React 19 + Vite 8 SPA (`react-router-dom`, `lucide-react`) | Vercel / Cloudflare Pages |
| Backend | FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic · Postgres 17 · Cloudinary · JWT (HS256) + Argon2id · nginx API gateway | Oracle VM (or any single host) |

The **`backend/` folder is a self-contained deploy unit** (`Dockerfile`, `docker-compose.yml`, `nginx.conf`, `.env.example`). Full architecture, threat model and runbook live in `docs/security/`.

## Prerequisites

- **Node.js 20+** (frontend) · **Python 3.12** (backend, matches `backend/Dockerfile`) · **Docker** (dev Postgres + ZAP scan)

## Development

```powershell
# 1. Database — dev Postgres on localhost:5432 (infyexchange/postgres/postgres)
cd backend
docker compose --profile dev up -d

# 2. Backend API — http://127.0.0.1:8000 (Swagger at /docs, non-prod only)
copy .env.example .env          # then set SECRET_KEY + the three CLOUDINARY_* values
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 3. Frontend — http://127.0.0.1:5173 (Vite proxies /api to :8000, so no CORS/base-URL needed)
cd .. ; npm install ; npm run dev
```

The app applies pending **Alembic migrations** on startup (fail-fast in production) and exposes `GET /health`. To add migrations after model changes, use `python -m alembic revision --autogenerate -m "..."` then `python -m alembic upgrade head`.

## Configuration

All backend settings live in `backend/.env`; the single annotated template for **both dev and prod** is **`backend/.env.example`**. Only these have **no default** and must be set: `SECRET_KEY`, `DATABASE_URL`, and `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET`. Everything else (mode, JWT TTL, CORS, rate limits, image caps, pooling, HSTS) is optional with a sane default — see the template for the full list. The frontend needs just `VITE_API_BASE_URL` (template: root **`.env.example`**; set it in the static host's dashboard, never in git). It is inlined at build time, so changing it means redeploying, and it must carry the gateway's `/api` path — the production build rejects a malformed value instead of shipping an SPA that 404s. Unset in dev because Vite proxies `/api`.

## Production deployment

Two deployments you connect by URL.

**Backend** (on the VM — `docker-compose.yml` `prod` profile runs `postgres` + `api` + an nginx **API gateway**):

```bash
cd backend
cp .env.example .env                       # set every CHANGE_ME; chmod 600 .env
docker compose --profile prod up -d --build   # only nginx publishes :80 (443 after TLS)
```

Postgres and the API sit on internal networks with **no published ports**; secrets fail fast on missing `${VAR:?}`; containers run with `cap_drop: ALL`, `read_only` nginx, resource/pids limits and `no-new-privileges`.

**Frontend** — build the static SPA and deploy `dist/` to Vercel / Cloudflare Pages, setting `VITE_API_BASE_URL` to the API origin **plus the `/api` path** (e.g. `https://<API_DOMAIN>/api`):

```bash
npm run build
```

**To connect them:** set the backend's `CORS_ORIGINS` to the exact frontend origin and the frontend's `VITE_API_BASE_URL` to the API origin plus `/api` — the origins must match or the browser blocks the calls. The SPA's own HTML-facing headers (CSP for the origin that holds the token) are **generated into `dist/_headers`** by `vite.config.js` from that same variable — Cloudflare Pages and Vercel both read the file from the output dir, so there is nothing to hand-maintain and no placeholder to forget; flip `CSP_ENFORCE` once the report-only burn-in is clean. Client-side routes need the `public/_redirects` fallback, which Vite copies into `dist/`. Enable `HSTS_ENABLED` only after HTTPS is verified. Step-by-step: `docs/security/SECURITY_RUNBOOK.md`.

## API & domain model

The REST API is namespaced under `/api` (`auth`, `users`, `listings`, `needs`, `interests`, `admin`) plus `GET /health`. Authenticated routes take `Authorization: Bearer <jwt>`; admin routes also require `is_admin`. **Exact endpoints are defined by the OpenAPI spec (`/docs` in a non-production environment) and `backend/app/routers/`** — not mirrored here. Domain facts (roles `SE/DSE/SP_L1/SP_L2`; listing types `SELL/RENT/LEND/GIVEAWAY` with price forced to `0` for lend/giveaway; statuses; interest lifecycle; expiry/cleanup; settings-driven rate limits) live in `backend/app/models`, `schemas/` and `config.py`.

Notable behaviours: an accepted interest reveals the counterparty's contact through a gated endpoint (`403` before acceptance, `200` for participants); duplicate submissions inside `DUPLICATE_SUBMISSION_WINDOW_SECONDS` return the existing record; a failed image upload rolls back the DB row and deletes any Cloudinary objects; admin/security actions write to an audit log; contact details are the only thing gated behind acceptance.

## Testing

```powershell
cd backend
python -m pytest              # security suite (SQLite isolation, no external services)
python -m bandit -r app       # static analysis
```

DAST runs against a live target via ZAP in Docker: `scripts/security/zap-api-scan.ps1` (needs a non-production `ENVIRONMENT`; reports land in `zap-reports/`). CI (`.github/workflows/ci.yml`) runs the frontend build + `npm audit` and the backend tests + `bandit` + `pip-audit`.

## Conventions

- **No hard-coded rules:** every policy lives in backend config/schemas; the client never duplicates validation logic or mocks API payloads. Forms declare constraints as HTML attributes and use the browser Constraint Validation API.
- **Fail loudly:** missing required secrets and failed production migrations surface immediately — no silent weak defaults.
- **Known trade-offs:** JWT in `localStorage` (cookie strategy pending); the rate limiter is per-process in-memory (needs Redis to scale horizontally).
- Account management (edit profile / change password / delete account) has **no backend API yet**, so those controls are intentionally absent — not placeholders.

## Repository layout

```
src/                    React SPA — app/App.jsx (routes + <Protected>), components/, context/AuthContext, pages/, services/api.js, utils/filters.js
backend/                FastAPI app (deploy unit)
  app/                  routers · schemas · models · services · utils · middleware · config · database · dependencies · main
  alembic/              Migrations          tests/  pytest security suite
  docker-compose.yml    profiles: dev (postgres) | prod (postgres + api + web)
  Dockerfile  nginx.conf  .env.example      requirements.txt (runtime + dev/security)
docs/security/          HLD · LLD · THREAT_MODEL · TEST_PLAN · SECURITY_RUNBOOK · ASSET_INVENTORY · ACCEPTANCE_CRITERIA
scripts/security/       zap-api-scan.ps1 · openapi_diff.py
vite.config.js          Dev proxy /api → http://127.0.0.1:8000
```
