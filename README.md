# InfyExchange

A campus marketplace for the Infosys Mysore trainee community: **buy, rent, lend and give away** items (sports equipment and more) within campus, plus a parallel "needs" board where trainees post what they are looking for and others offer items via interests. Accepted interests unlock a contact exchange, and an admin control plane provides moderation, user management and an audit trail.

Monorepo with two applications:

| Layer | Tech | Location |
|---|---|---|
| Frontend | React 19 + Vite 8 SPA (`react-router-dom`, `lucide-react`) | `src/` |
| Backend | FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic migrations | `backend/app/` |
| Database | PostgreSQL 17 (Docker Compose; pooled psycopg 3 connections) | `backend/docker-compose.yml` |
| Image storage | Cloudinary (upload/delete + magic-byte validation) | `backend/app/services/cloudinary.py` |
| Auth | JWT (HS256, PyJWT) + Argon2id password hashing (pinned hasher, `pwdlib`) | `backend/app/services/auth.py` |
| Edge / deployment | nginx (rate limiting, CSP, SPA fallback) + hardened production compose | `nginx.conf`, `docker-compose.prod.yml` |
| Security docs & tests | HLD/LLD/threat-model runbooks + pytest security suite + OWASP ZAP automation | `docs/security/`, `backend/tests/`, `scripts/security/` |

---

## Repository layout

```
├── src/                        # React client
│   ├── app/App.jsx             # Routes + <Protected> (JWT + adminOnly) + ErrorBoundary
│   ├── components/             # Layout (header/sidebar/footer), cards, UI, ErrorBoundary
│   ├── context/AuthContext     # Token in localStorage (`infy_token`), /api/auth/me bootstrap
│   ├── pages/                  # Home, Auth, Marketplace, Needs, Posting, Account, Admin, NotFound
│   ├── services/api.js         # fetch wrapper: ApiError, 401 clearance, retries, detail flattening
│   └── utils/filters.js        # Shared client-side filter helpers
├── backend/
│   ├── app/
│   │   ├── routers/            # auth, users, listings, interests, needs, admin (all under /api/*)
│   │   ├── schemas/            # Pydantic request/response models = validation source of truth
│   │   ├── models/             # User, Listing, ListingImage, Need, Interest, AuditLog
│   │   ├── services/           # auth (JWT/Argon2id), cloudinary, cleanup, rate limiting, migration
│   │   ├── utils/              # enums.py (domain states), logging_utils.py (UTC + security logger)
│   │   ├── middleware.py       # SecurityHeaders + RequestContext (X-Request-ID, no-store)
│   │   ├── config.py           # pydantic-settings, reads backend/.env
│   │   ├── database.py         # Engine/session from DATABASE_URL (pool size/recycle via config)
│   │   ├── dependencies.py     # Bearer-token → current user resolution
│   │   ├── run_cleanup.py      # Manual one-shot cleanup runner
│   │   └── main.py             # Lifespan: Alembic upgrade + cleanup loop; docs gated by env;
│   │                           #   exception handlers (422 flattening, DB errors masked as 500)
│   ├── alembic/                # Migration scripts (initial schema versioned)
│   ├── tests/                  # pytest security suite: auth, authorization, validation, headers
│   ├── docker-compose.yml      # dev: postgres:17 only (db `infyexchange`, 5432)
│   ├── Dockerfile              # API image (uvicorn on :8000)
│   ├── .env.example            # Dev environment contract (copy to backend/.env)
│   ├── requirements.txt        # Pinned runtime deps
│   ├── requirements-dev.txt    # pytest, httpx, pytest-cov, bandit
│   ├── alembic.ini / pytest.ini
├── docs/security/              # HLD, LLD, THREAT_MODEL, TEST_PLAN, SECURITY_RUNBOOK,
│                               #   ASSET_INVENTORY, ACCEPTANCE_CRITERIA
├── scripts/security/           # zap-api-scan.ps1 (ZAP DAST) + openapi_diff.py (offered-vs-consumed gate)
├── docker-compose.prod.yml     # prod: postgres + api + nginx web, secrets via `:?` fail-fast
├── nginx.conf                  # Edge: limit_req/limit_conn, report-only CSP, SPA fallback, /api proxy
├── .env.prod.example           # Root env template for the production stack (copy to .env)
└── vite.config.js              # Dev proxy: /api → http://127.0.0.1:8000
```

---

## Prerequisites

- **Node.js 20+** (frontend, Vite)
- **Python 3.12** (backend; matches `backend/Dockerfile`)
- **Docker Desktop** (PostgreSQL container; also used by the ZAP scan script)

---

## Quickstart (development)

### 1. Database

```powershell
cd backend
docker compose up -d          # postgres:17 on localhost:5432, db/user/pass: infyexchange/postgres/postgres
```

### 2. Backend

```powershell
cd backend
copy .env.example .env        # then fill in SECRET_KEY and Cloudinary credentials (see table below)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # runtime + test tooling (use requirements.txt for prod-only)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On startup the app applies pending **Alembic migrations** (`upgrade head`; a failed migration hard-stops the process in production, stays lenient in development) and launches the background cleanup task. Check `GET http://127.0.0.1:8000/health`; Swagger/Redoc are served at `/docs` and `/redoc` only when `ENVIRONMENT` is not `production`.

To create new migrations after model changes, always invoke Alembic as a module (the venv launcher can hold a stale absolute path on Windows):

```powershell
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"
.venv\Scripts\python.exe -m alembic upgrade head
```

### 3. Frontend

```powershell
npm install
npm run dev                   # vite --host 127.0.0.1 → http://127.0.0.1:5173
```

The client calls relative `/api/...` paths; Vite proxies them to `http://127.0.0.1:8000`, so no CORS or base-URL configuration is needed in development. For split-origin builds set `VITE_API_BASE_URL` (inlined at build time — changing it requires a rebuild).

---

## Environment variables (`backend/.env`)

| Variable | Purpose | Default / example |
|---|---|---|
| `APP_NAME`, `ENVIRONMENT` | Metadata / mode (`production` gates docs + fail-fast migrations) | `InfyExchange`, `development` |
| `DATABASE_URL` | SQLAlchemy DSN (psycopg 3) | `postgresql+psycopg://postgres:postgres@localhost:5432/infyexchange` |
| `SECRET_KEY` | JWT signing key — **required, no default** | long random string |
| `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT policy | `HS256`, `10080` (7 days) |
| `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET` | Image storage credentials — **required, no default** | from Cloudinary console |
| `LISTING_EXPIRY_DAYS` | TTL for listings/needs before cleanup deletes them | `30` |
| `MAX_IMAGES_PER_LISTING`, `MAX_IMAGE_SIZE_MB` | Upload policy enforced by the listings router | `5`, `5` |
| `DUPLICATE_SUBMISSION_WINDOW_SECONDS` | Identical re-submission inside the window returns the existing record | `60` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE` | Connection pooling for PostgreSQL | `10`, `20`, `1800` |
| `CORS_ORIGINS` | Exact comma-separated origins (never `*`; `allow_credentials` is on) | `http://localhost:4200` |
| `ALLOWED_EMAIL_DOMAINS` | Registration domains enforced by `/api/auth/register` | `gmail.com` |
| `REFERRER_POLICY`, `PERMISSIONS_POLICY`, `API_CSP` | Security-header values applied by middleware | sensible defaults in `config.py` |
| `HSTS_ENABLED`, `HSTS_MAX_AGE`, `HSTS_INCLUDE_SUBDOMAINS` | HSTS — enable only after HTTPS coverage is confirmed (runbook) | `false`, `15552000`, `false` |
| `ALLOWED_HOSTS` | Host-header allowlist (`TrustedHostMiddleware`); empty disables | – |
| `RATE_LIMIT_WINDOW_SECONDS` + `RATE_LIMIT_LOGIN/REGISTER/CREATE/READ/CONTACT/ADMIN` | Settings-driven rate limits → `429` | `60`; `10/5/10/120/20/60` |

---

## API surface

All routers live under `/api`. Authenticated endpoints expect `Authorization: Bearer <jwt>`; admin endpoints additionally require `is_admin`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register` (201), `POST /api/auth/login`, `GET /api/auth/me` |
| Users | `GET /api/users/me`, `GET /api/users/me/summary` (activity counts) |
| Listings | `GET /api/listings` (filters: `search`, `category`, `listing_type`, `location`, `condition`, `min_price`, `max_price`; pagination `skip`/`limit` ≤ 100), `GET /api/listings/me`, `GET /api/listings/{id}`, `POST /api/listings` (multipart with images), `PUT /api/listings/{id}`, `DELETE /api/listings/{id}` |
| Needs | `GET /api/needs`, `GET /api/needs/me`, `GET /api/needs/{id}`, `POST /api/needs`, `DELETE /api/needs/{id}` |
| Interests | `POST /api/interests/listing/{id}`, `GET /api/interests/sent`, `GET /api/interests/received`, `PATCH /api/interests/{id}/accept`, `PATCH /api/interests/{id}/reject`, `GET /api/interests/{id}/contact` (owner contact revealed only after acceptance) |
| Admin | `GET /api/admin/stats`, `GET/PATCH /api/admin/users[/{id}]` (activate/suspend), `GET /api/admin/listings`, `PATCH /api/admin/listings/{id}/status`, `DELETE /api/admin/listings/{id}`, `GET /api/admin/needs`, `DELETE /api/admin/needs/{id}`, `GET /api/admin/audit-logs` |
| Ops | `GET /`, `GET /health` |

### Domain rules encoded in the backend

- **Roles:** `SE`, `DSE`, `SP_L1`, `SP_L2` (registration field).
- **Listing types:** `SELL`, `RENT`, `LEND`, `GIVEAWAY` — price is forced to `0` for `LEND`/`GIVEAWAY`.
- **Categories:** sports equipment (badminton, table tennis, pool/snooker, squash, tennis, cricket, football, basketball) + `OTHER`; conditions `NEW`…`POOR`.
- **Listing status:** `ACTIVE` → `SOLD`/`RENTED`/`UNAVAILABLE`; only `ACTIVE` + unexpired listings appear in the public catalogue. Admins change status from the control plane.
- **Needs:** `BUY`, `RENT`, `BORROW`; lifecycle `ACTIVE` → `FULFILLED`/`CLOSED`.
- **Interests:** `PENDING` → `ACCEPTED`/`REJECTED`; listing owners cannot interest their own listing (validated server-side). Contact details are exchanged only after acceptance.
- **Double-submit defense:** identical listing/need re-submission inside `DUPLICATE_SUBMISSION_WINDOW_SECONDS` returns the existing record instead of creating a duplicate.
- **Expiry:** listings/needs carry `expires_at` (`LISTING_EXPIRY_DAYS`); a background loop runs every 24 h, deleting expired rows **and their Cloudinary images** (manual trigger: `python -m app.run_cleanup`). Failed listing creation rolls back the DB row and deletes already-uploaded images.
- **Rate limits (settings-driven, in-memory):** per-IP windows for login/register/create/read/contact/admin plus a **per-account** login key that blunts distributed brute force; violations return `429` with `Retry-After`; tracked-key memory is bounded.
- **Audit trail:** admin/security-relevant actions are written to an `AuditLog` table and queryable at `GET /api/admin/audit-logs`.
- **Uploads:** image magic bytes validated, count/size capped by config; nginx allows bodies up to 30 MB at the edge.

---

## Validation & error architecture (single source of truth)

- **Backend:** Pydantic schemas in `backend/app/schemas/` declare every rule (field lengths, `EmailStr`, enums, dates); config-driven policies (email domains, image caps, rate limits) come from `settings`, never literals. A `RequestValidationError` handler in `main.py` flattens FastAPI's structured `422` detail into readable `"field: msg"` strings, and `SQLAlchemyError`/unhandled exceptions are logged and masked as generic `500`s.
- **Frontend:** forms declare constraints as HTML attributes (`required`, `minLength`, `maxLength`, `pattern`, `type="email"`); `AuthPage` runs them through the Constraint Validation API on submit (`noValidate` + `:invalid`/`validationMessage`), and cross-field rules (confirm password) use `setCustomValidity`. No rule is duplicated in JavaScript.
- **Error path:** `src/services/api.js` normalizes `detail` (string *or* array) into human-readable `ApiError` messages with `status` and raw payload attached. `401` responses clear the stored token and dispatch an `auth:expired` event for graceful auto-logout; idempotent GETs pass a bounded retry count for transient network drops (exponential backoff).
- **Error UI:** `ErrorBoundary` catches render crashes; `NotFoundPage` handles unknown routes; generic status/empty-state copy belongs in a constants module, never mirrored validation rules.

---

## Security controls (see `docs/security/` for the full runbook)

- **API middleware** (`backend/app/middleware.py`): security headers (CSP, `Referrer-Policy`, `Permissions-Policy`, `X-Content-Type-Options`, HSTS gated by `HSTS_ENABLED`), `Cache-Control: no-store` on authenticated responses, and `X-Request-ID` correlation on every request/response.
- **Structured logging** with UTC timestamps and a dedicated `security` logger (`backend/app/utils/logging_utils.py`).
- **Edge hardening** (`nginx.conf`): `limit_req`/`limit_conn` zones, report-only CSP allowlisting Google Fonts + Cloudinary, dotfile denial (with `/.well-known` exception), `server_tokens off`, gzip, SPA fallback with `/api/*` reverse proxy.
- **Production topology** (`docker-compose.prod.yml`): three services (`postgres`, `api`, `web`), Postgres isolated on an internal network with no published port, secrets required via `${VAR:?}` fail-fast interpolation, `cap_drop: ALL`, `read_only` nginx with tmpfs, resource/pids limits, `no-new-privileges`, health-checked dependency ordering.
- **Startup hardening:** docs/OpenAPI disabled in `production`, migrations fail-fast in `production`, optional `ALLOWED_HOSTS` Host-header validation.

---

## Testing

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m pytest                       # security suite (SQLite isolation, no external services)
python -m bandit -r app                # static analysis
```

The suite covers auth flows, authorization boundaries, input validation and security headers (`backend/tests/`). DAST automation runs against a live target via ZAP in Docker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1
# or baseline scan of the SPA:  -Mode baseline -Target http://host.docker.internal:5173
```

Reports land in `zap-reports/`. Note the OpenAPI target requires a non-production `ENVIRONMENT`.

---

## Production deployment

```powershell
npm run build                            # SPA bundle into dist/ (mounted read-only by nginx)
copy .env.prod.example .env              # root .env — fill every secret, NEVER commit it
docker compose -f docker-compose.prod.yml up -d --build
```

The stack serves the SPA + reverse-proxied API on port 80. `VITE_API_BASE_URL` can stay unset (same-origin `/api`); behind the proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips='*'` so per-IP rate limiting sees real client IPs. Enable `HSTS_ENABLED` only after HTTPS coverage is verified (see `docs/security/SECURITY_RUNBOOK.md`).

---

## Frontend routes

| Route | View | Guarded |
|---|---|---|
| `/` | Home (latest live listings) | – |
| `/login`, `/register` | Auth forms | – |
| `/listings`, `/listings/:id` | Catalogue + detail (interest action, contact after accept) | – |
| `/needs` | Needs board | – |
| `/listings/new`, `/needs/new` | Posting forms (listing / need) | ✔ |
| `/profile`, `/activity` | Account + activity summary | ✔ |
| `/my-listings`, `/my-needs` | Own listings / needs management | ✔ |
| `/admin` | Admin control plane (stats, users, listings, needs, audit logs) | ✔ admin-only |
| `*` | `NotFoundPage` | – |

Guarded routes use the `<Protected>` wrapper in `src/app/App.jsx` (redirects to `/login` until `GET /api/auth/me` resolves; `adminOnly` redirects non-admins to `/profile`).

---

## Scripts & operations

| Command | Effect |
|---|---|
| `npm run dev` | Vite dev server on `127.0.0.1:5173` with `/api` proxy |
| `npm run build` / `npm run preview` | Production bundle into `dist/` / local preview |
| `uvicorn app.main:app --reload` (in `backend/`) | API on `127.0.0.1:8000` with Swagger at `/docs` (non-prod) |
| `docker compose up -d` / `down` (in `backend/`) | Dev PostgreSQL (named volume `postgres_data`; `down -v` wipes data) |
| `python -m alembic revision --autogenerate` / `upgrade head` / `downgrade -1` | Schema migrations (always via `python -m alembic`, startup auto-applies) |
| `python -m pytest` (in `backend/`) | Security test suite |
| `python -m bandit -r app` (in `backend/`) | Python static security analysis |
| `scripts/security/zap-api-scan.ps1` | OWASP ZAP DAST (openapi / baseline) with HTML/MD/JSON reports |
| `docker compose -f docker-compose.prod.yml up -d --build` | Full hardened production stack |

---

## Project conventions

- **No hard-coded data or rules:** every policy lives in backend config/schemas; the client never duplicates validation logic or mocks API payloads in views.
- **Service layer boundary:** views talk only to `src/services/api.js`; persistence talks only through SQLAlchemy sessions; Cloudinary is isolated in its service.
- **Fail loudly:** missing required secrets (`${VAR:?}` in prod compose, no-default settings like `SECRET_KEY`/Cloudinary) and failed migrations in production surface immediately — no silent weak defaults.
- **Fail-safe writes:** listing creation rolls back the DB row and deletes uploaded Cloudinary objects on failure.
- **Known trade-offs:** JWT in `localStorage` (XSS exposure, cookie strategy pending); rate limiter is per-process in-memory (needs Redis/shared store for multi-instance scaling).
- **Not yet shipped:** (1) Account management (edit profile, change password, delete account) has no backend API, so those UI controls are intentionally absent — not placeholders. (2) **Contact reveal:** the gated endpoint `GET /api/interests/{id}/contact` is implemented and live-verified (403 before acceptance / to third parties, 200 with details for participants), but the SPA does not yet call it — the post-acceptance exchange is unusable from the UI until that wiring ships.
