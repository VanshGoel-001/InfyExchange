# InfyExchange

A campus marketplace for the Infosys Mysore trainee community: **buy, rent, lend and give away** items (sports equipment and more) within campus, plus a parallel "needs" board where trainees post what they are looking for and others offer items via interests.

Monorepo with two applications:

| Layer | Tech | Location |
|---|---|---|
| Frontend | React + Vite SPA (`react-router-dom`, `lucide-react`) | `src/` |
| Backend | FastAPI + SQLAlchemy 2 + Pydantic v2 | `backend/app/` |
| Database | PostgreSQL 17 (Docker Compose) | `backend/docker-compose.yml` |
| Image storage | Cloudinary (upload/delete + magic-byte validation) | `backend/app/services/cloudinary.py` |
| Auth | JWT (HS256, PyJWT) + Argon2 password hashing (`pwdlib`) | `backend/app/services/auth.py` |

---

## Repository layout

```
├── src/                      # React client
│   ├── app/App.jsx           # Routes + <Protected> guard (JWT-based)
│   ├── components/           # Layout (header/sidebar/footer), cards, UI primitives
│   ├── context/AuthContext   # Token in localStorage (`infy_token`), /api/auth/me bootstrap
│   ├── pages/                # Home, Auth (login/register), Marketplace, Needs, Posting, Account
│   └── services/api.js       # Single service layer: fetch wrapper + ApiError, Vite /api proxy
├── backend/
│   ├── app/
│   │   ├── routers/          # auth, users, listings, interests, needs (all under /api/*)
│   │   ├── schemas/          # Pydantic request/response models = validation source of truth
│   │   ├── models/           # SQLAlchemy models: User, Listing, ListingImage, Need, Interest
│   │   ├── services/         # auth (JWT/hash), cloudinary, cleanup loop, rate limiting
│   │   ├── utils/enums.py    # Roles, listing types/categories/conditions, interest & need states
│   │   ├── config.py         # pydantic-settings, reads backend/.env
│   │   ├── database.py       # Engine/session from DATABASE_URL
│   │   ├── dependencies.py   # Bearer-token → current user resolution
│   │   └── main.py           # App factory: table creation, cleanup task, CORS, routers
│   ├── docker-compose.yml    # postgres:17 only (db `infyexchange`, 5432)
│   ├── Dockerfile            # python:3.12-slim, uvicorn on :8000
│   ├── .env.example          # Environment contract (copy to .env)
│   └── requirements.txt
└── vite.config.js            # Dev proxy: /api → http://127.0.0.1:8000
```

---

## Prerequisites

- **Node.js 20+** (frontend, Vite)
- **Python 3.12** (backend; matches `backend/Dockerfile`)
- **Docker Desktop** (PostgreSQL container)

---

## Quickstart

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
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On startup the app creates all tables (`Base.metadata.create_all`) and launches a background cleanup task. Check `GET http://127.0.0.1:8000/health` and the interactive docs at `http://127.0.0.1:8000/docs`.

### 3. Frontend

```powershell
npm install
npm run dev                   # vite --host 127.0.0.1 → http://127.0.0.1:5173
```

The client calls relative `/api/...` paths; Vite proxies them to `http://127.0.0.1:8000`, so no CORS or base-URL configuration is needed in development.

---

## Environment variables (`backend/.env`)

| Variable | Purpose | Default / example |
|---|---|---|
| `APP_NAME`, `ENVIRONMENT` | Metadata / mode | `InfyExchange`, `development` |
| `DATABASE_URL` | SQLAlchemy DSN (psycopg 3) | `postgresql+psycopg://postgres:postgres@localhost:5432/infyexchange` |
| `SECRET_KEY` | JWT signing key — **required, no default** | long random string |
| `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT policy | `HS256`, `10080` (7 days) |
| `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET` | Image storage credentials — **required, no default** | from Cloudinary console |
| `LISTING_EXPIRY_DAYS` | TTL for listings/needs before cleanup deletes them | `30` |
| `MAX_IMAGES_PER_LISTING`, `MAX_IMAGE_SIZE_MB` | Upload policy enforced by the listings router | `5`, `5` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:4200` |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated registration domains enforced by `/api/auth/register` | `gmail.com` |

---

## API surface

All routers live under `/api`. Authenticated endpoints expect `Authorization: Bearer <jwt>`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register` (201), `POST /api/auth/login`, `GET /api/auth/me` |
| Listings | `GET /api/listings`, `GET /api/listings/me`, `GET /api/listings/{id}`, `POST /api/listings` (multipart with images), `DELETE /api/listings/{id}` |
| Needs | `GET /api/needs`, `GET /api/needs/me`, `POST /api/needs` |
| Interests | `POST /api/interests/listing/{id}`, `GET /api/interests/sent`, `GET /api/interests/received`, `PATCH /api/interests/{id}/accept`, `PATCH /api/interests/{id}/reject` |
| Users | `GET /api/users/me/summary` (activity counts) |
| Ops | `GET /`, `GET /health` |

### Domain rules encoded in the backend

- **Roles:** `SE`, `DSE`, `SP_L1`, `SP_L2` (registration field).
- **Listing types:** `SELL`, `RENT`, `LEND`, `GIVEAWAY` — price is forced to `0` for `LEND`/`GIVEAWAY`.
- **Categories:** sports equipment (badminton, table tennis, pool/snooker, squash, tennis, cricket, football, basketball) + `OTHER`; conditions `NEW`…`POOR`.
- **Needs:** `BUY`, `RENT`, `BORROW`; lifecycle `ACTIVE` → `FULFILLED`/`CLOSED`.
- **Interests:** `PENDING` → `ACCEPTED`/`REJECTED`; listing owners cannot interest their own listing (ownership validated server-side).
- **Expiry:** listings/needs carry `expires_at` (`LISTING_EXPIRY_DAYS`); a background loop runs every 24 h, deleting expired rows **and their Cloudinary images** (rollback-safe: failed listing creation deletes already-uploaded images).
- **Rate limits (in-memory, per IP):** login 10/min, register 5/min → `429`.
- **Uploads:** image magic bytes validated, count/size capped by config.

---

## Validation architecture (single source of truth)

- **Backend:** Pydantic schemas in `backend/app/schemas/` declare every rule (field lengths, `EmailStr`, enums, dates); config-driven policies (email domains, image caps) come from `settings`, never literals. Violations return `422` with a structured `detail` array (`[{loc, msg, …}]`).
- **Frontend:** forms declare constraints as HTML attributes (`required`, `minLength`, `maxLength`, `pattern`, `type="email"`); `AuthPage` runs them through the Constraint Validation API on submit (`noValidate` + `:invalid`/`validationMessage`), and cross-field rules (confirm password) use `setCustomValidity`. No rule is duplicated in JavaScript.
- **Error path:** `src/services/api.js` maps the backend's structured `detail` into human-readable `ApiError` messages, so server-side validator output reaches the UI verbatim.

---

## Frontend routes

| Route | View | Guarded |
|---|---|---|
| `/` | Home (latest live listings) | – |
| `/login`, `/register` | Auth forms | – |
| `/listings`, `/listings/:id` | Catalogue + detail (interest action) | – |
| `/needs` | Needs board | – |
| `/listings/new`, `/needs/new` | Posting forms (listing / need) | ✔ |
| `/profile`, `/activity` | Account + activity summary | ✔ |
| `/my-listings`, `/my-needs` | Own listings / needs management | ✔ |
| `*` | Redirect to `/` | – |

Guarded routes use the `<Protected>` wrapper in `src/app/App.jsx`, redirecting to `/login` until `GET /api/auth/me` resolves.

---

## Scripts & operations

| Command | Effect |
|---|---|
| `npm run dev` | Vite dev server on `127.0.0.1:5173` with `/api` proxy |
| `npm run build` | Production bundle into `dist/` |
| `uvicorn app.main:app --reload` (in `backend/`) | API on `127.0.0.1:8000` with Swagger at `/docs` |
| `docker compose up -d` / `down` (in `backend/`) | Start/stop PostgreSQL (named volume `postgres_data`; `down -v` wipes data) |
| `docker build -t infyexchange-api backend/` | Containerized API image (uvicorn on :8000) |

---

## Project conventions

- **No hard-coded data or rules:** every policy lives in backend config/schemas; the client never duplicates validation logic or mocks API payloads in views.
- **Service layer boundary:** views talk only to `src/services/api.js`; persistence talks only through SQLAlchemy sessions; Cloudinary is isolated in its service.
- **Fail-safe writes:** listing creation rolls back the DB row and deletes uploaded Cloudinary objects on failure.
- **Known trade-offs:** JWT in `localStorage` (XSS exposure, cookie strategy pending); rate limiter is per-process in-memory; profile-editing/change-password APIs do not exist yet, so related UI controls are placeholders.
