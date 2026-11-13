# Getting Started

This page takes you from a fresh clone to a working local stack: PostgreSQL in Docker, the FastAPI API, and the Vite dev server.

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| Node.js | 20+ (CI uses 22) | Frontend build and dev server |
| Python | 3.12 | Backend (CI and the Docker image use 3.12) |
| Docker with Compose | recent | Local PostgreSQL 17 |
| A Cloudinary account | free tier is fine | The backend refuses to start without Cloudinary settings, even if you never upload an image |

## 1. Start PostgreSQL

```powershell
cd backend
docker compose up -d
```

This runs `postgres:17-alpine` as `infyexchange-postgres-dev`, bound to `127.0.0.1:5432` only, with user/password `postgres`/`postgres` and database `infyexchange`. Data lives in the named volume `postgres_dev_data`; `docker compose down -v` wipes it.

## 2. Configure and start the API

```powershell
cd backend
Copy-Item .env.example .env
# Edit .env: set SECRET_KEY and the three CLOUDINARY_* values.
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # runtime + pytest/bandit/pip-audit; production installs requirements.txt only
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

> **Run from `backend/`.** Two things resolve relative to the working directory: `.env` (pydantic-settings reads `env_file=".env"`) and `alembic.ini` (the migration runner calls `Config("alembic.ini")`). Starting uvicorn from the repository root will fail to find your settings.

On startup the API:

1. Applies pending Alembic migrations (see [Backend Guide](Backend-Guide.md#startup-and-migrations)).
2. Starts the daily expired-data cleanup loop.
3. Serves `/health`, and `/docs` + `/redoc` + `/openapi.json` (disabled when `ENVIRONMENT=production`).

Required variables (the process exits at import time if any are missing): `DATABASE_URL`, `SECRET_KEY`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`. All others have defaults – see the [Configuration Reference](Configuration-Reference.md).

## 3. Start the frontend

From the repository root:

```powershell
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies every `/api` request to `http://127.0.0.1:8000`, so the browser sees a single origin: CORS is never exercised in development and `VITE_API_BASE_URL` can stay unset.

## 4. Create your first accounts

1. Go to `/register`. Only addresses ending in an allowed domain are accepted – by default **`@gmail.com` only** (`ALLOWED_EMAIL_DOMAINS`).
2. Password rules: 8–100 characters with at least one letter and one digit. Phone: 10–15 characters, unique. You must pick a role (`SE`, `DSE`, `SP_L1`, `SP_L2`) and a joining date.
3. Registration logs you in automatically and lands you on `/profile`.

### Making yourself an admin

There is **no API or UI to create the first admin** – `is_admin` defaults to `false` and registration never sets it. Promote an account directly in the database:

```powershell
docker exec -it infyexchange-postgres-dev psql -U postgres -d infyexchange `
  -c "UPDATE users SET is_admin = true WHERE email = 'you@gmail.com';"
```

Log out and back in (or reload) and an **Admin Panel** entry appears in the account menu, routing to `/admin`. Once one admin exists, they can promote or demote others from the Users tab; the API forbids an admin from revoking their own admin rights.

## 5. Verify your setup

```powershell
# Frontend (repo root)
npm audit --audit-level=high
npm run build

# Backend (from backend/)
python -m pytest -q
python -m bandit -r app -q
python -m pip_audit -r requirements.txt --progress-spinner off
```

These are the same gates CI runs. The tests use a temporary SQLite file and fake Cloudinary credentials, so they need neither Docker nor your `.env`. See [Testing](Testing.md).

## Everyday commands

| Task | Command |
| --- | --- |
| Run the API with reload | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` (in `backend/`) |
| Run the dev frontend | `npm run dev` |
| Production build of the SPA | `npm run build` (emits `dist/` including a generated `_headers`) |
| Preview the production build | `npm run preview` |
| Create a migration | `alembic revision --autogenerate -m "describe change"` (in `backend/`) |
| Apply migrations manually | `alembic upgrade head` (in `backend/`; uses `DATABASE_URL_UNPOOLED` if set) |
| Run expiry cleanup once | `python -m app.run_cleanup` (in `backend/`) |
| Check for dead/broken API calls | `python scripts/security/openapi_diff.py` |
| ZAP scan of the local API | `powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1` |

## Common first-run problems

| Symptom | Cause / fix |
| --- | --- |
| `ValidationError: ... field required` when starting uvicorn | A required env var is missing, or you started from the wrong directory (see the note above). |
| API starts but every request returns 500 about a missing table | Migrations failed. In non-production the failure is logged and **swallowed** so the app still starts – read the log for `Database migrations failed`. Check Postgres is up and `DATABASE_URL` matches the Compose credentials. |
| Browser shows CORS errors | You bypassed the Vite proxy (e.g. set `VITE_API_BASE_URL` to `http://127.0.0.1:8000/api`). Unset it, or add the frontend origin to `CORS_ORIGINS`. |
| `Only Gmail addresses are allowed` on register | Expected with the default `ALLOWED_EMAIL_DOMAINS=gmail.com`. |
| `429 Too many ...` while testing | In-memory rate limits (e.g. 10 logins/min/IP). Wait a minute or restart the API – the counters live in process memory. |
| Production `vite build` throws about `VITE_API_BASE_URL` | In production mode the value must end in `/api` with no trailing slash (see [Frontend Guide](Frontend-Guide.md#build-time-api-url-validation)). |
