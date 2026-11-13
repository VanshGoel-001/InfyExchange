# Configuration Reference

## Backend (`backend/app/config.py`)

Settings are read from environment variables (case-insensitive) and `backend/.env`. Template: [backend/.env.example](../backend/.env.example). Unknown variables are ignored.

### Required

The process fails at import if any of these is missing.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL for the **runtime** engine. Use the `postgresql+psycopg://` scheme (psycopg 3). In production this is Neon's **pooled** connection with `sslmode=require` |
| `SECRET_KEY` | JWT signing key. Long and random; rotating it logs everyone out |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Cloudinary credentials (configured at import time) |

### Database

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL_UNPOOLED` | unset | Direct connection used by Alembic and the startup migration (falls back to `DATABASE_URL`). Needed with Neon because the pooler does not suit advisory locks/DDL |
| `DB_POOL_SIZE` | 10 | Cloud Run deploy sets 3 |
| `DB_MAX_OVERFLOW` | 20 | Cloud Run deploy sets 2 |
| `DB_POOL_RECYCLE` | 1800 s | Recycle connections before server-side idle timeouts |

### Application

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` disables docs/OpenAPI and makes migration failures fatal. Tests use `test` |
| `APP_NAME` | `InfyExchange` | FastAPI title |
| `ALGORITHM` | `HS256` | JWT algorithm (also the only one accepted on decode) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 10080 | 7 days |
| `CORS_ORIGINS` | `http://localhost:4200` | Comma-separated **exact** origins; never `*`. Set to the Pages origin in production. (Vite dev runs on 5173 but proxies, so CORS is not used locally) |
| `ALLOWED_EMAIL_DOMAINS` | `gmail.com` | Comma-separated; empty falls back to `gmail.com` |
| `GOOGLE_CLIENT_ID` | empty | OAuth client ID of the Google Sign-In web client (public, not a secret). Empty switches "Sign in with Google" off (`POST /auth/google` answers `503`). Set it from the `GOOGLE_CLIENT_ID` GitHub variable: the deploy uses `--set-env-vars`, which replaces the whole set, so a value set by hand in the console is lost on the next deploy |
| `ALLOWED_HOSTS` | empty | If non-empty, enables `TrustedHostMiddleware` with this comma-separated list |

### Marketplace policy

| Variable | Default | Notes |
| --- | --- | --- |
| `LISTING_EXPIRY_DAYS` | 30 | Used for both listings and needs |
| `MAX_IMAGES_PER_LISTING` | 5 | Mirror in `PostingPage.jsx` |
| `MAX_IMAGE_SIZE_MB` | 5 | Mirror in `PostingPage.jsx` |
| `DUPLICATE_SUBMISSION_WINDOW_SECONDS` | 60 | Idempotency window for creating listings/needs |

### Security headers

| Variable | Default |
| --- | --- |
| `REFERRER_POLICY` | `strict-origin-when-cross-origin` |
| `PERMISSIONS_POLICY` | `camera=(), microphone=(), geolocation=(), payment=()` |
| `API_CSP` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` |
| `HSTS_ENABLED` | `false` (Cloud Run deploy sets `true`) |
| `HSTS_MAX_AGE` | `15552000` |
| `HSTS_INCLUDE_SUBDOMAINS` | `false` |

> `REFERRER_POLICY`, `PERMISSIONS_POLICY` and `API_CSP` are real settings but are **not** listed in `.env.example`.

### Rate limits

Window `RATE_LIMIT_WINDOW_SECONDS` = 60. Per-process, sliding window.

| Variable | Default |
| --- | --- |
| `RATE_LIMIT_LOGIN` | 10 (applied per IP and per account) |
| `RATE_LIMIT_REGISTER` | 5 |
| `RATE_LIMIT_CREATE` | 10 |
| `RATE_LIMIT_READ` | 120 |
| `RATE_LIMIT_CONTACT` | 20 |
| `RATE_LIMIT_ADMIN` | 60 |

### Container

| Variable | Default | Notes |
| --- | --- | --- |
| `PORT` | 8080 | Set by Cloud Run; the Dockerfile's `CMD` and `HEALTHCHECK` honour it |

The container runs: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*' --limit-concurrency 200 --timeout-keep-alive 30`.

## Frontend

| Variable | Where set | Notes |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Pages build settings / GitHub variable / local `.env` (optional) | Must end in `/api`, no trailing slash, in production builds. Unset → `/api` on the SPA origin. **Inlined at build time** |
| `VITE_GOOGLE_CLIENT_ID` | Pages build settings / GitHub variable / local `.env` (optional) | The same OAuth client ID as the backend's `GOOGLE_CLIENT_ID`. Empty hides the Google button. When set, `vite.config.js` also adds Google's script, frame and connect sources to the (report-only) CSP. **Inlined at build time** |

Template: [.env.example](../.env.example). Caution: its comments still mention `backend/nginx.conf` and a "VM" deployment from an older architecture; the current production layout is Pages + Cloud Run (see [Known Limitations](Known-Limitations-and-Gaps.md)).

## GitHub Actions variables and secrets

Configured on the repository or the `neon-staging` environment.

| Name | Type | Used by | Purpose |
| --- | --- | --- | --- |
| `GCP_PROJECT_ID` | variable | Cloud Run workflow | Google Cloud project |
| `GCP_REGION` | variable | Cloud Run workflow | Region for Cloud Run and Artifact Registry |
| `CLOUD_RUN_SERVICE` | variable | Cloud Run workflow | Service name |
| `ARTIFACT_REGISTRY_REPOSITORY` | variable | Cloud Run workflow | Pre-created Docker repository |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | variable | Cloud Run workflow | Full WIF provider resource name |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | variable | Cloud Run workflow | Deployer service account email |
| `CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT` | variable | Cloud Run workflow | Runtime service account email |
| `CORS_ORIGINS` | variable | Cloud Run workflow | Exact Pages origin |
| `CLOUDFLARE_ACCOUNT_ID` | variable | Pages workflow | Cloudflare account |
| `CLOUDFLARE_PAGES_PROJECT` | variable | Pages workflow | Pages project name |
| `VITE_API_BASE_URL` | variable | Pages workflow | `https://<api-host>/api` |
| `VITE_GOOGLE_CLIENT_ID` | variable (optional) | Pages workflow | Google OAuth client ID; empty = no Google button |
| `GOOGLE_CLIENT_ID` | variable (optional) | Cloud Run workflow | Same client ID for the API; empty = Google sign-in off |
| `CLOUDFLARE_API_TOKEN` | **secret** | Pages workflow | Pages deploy token |

Both workflows fail fast with a clear message if a required value is missing.

## Google Secret Manager secrets

Mapped by `gcloud run deploy --set-secrets`:

| Secret name | Injected as env var |
| --- | --- |
| `NEON_DATABASE_URL` | `DATABASE_URL` |
| `NEON_DATABASE_URL_UNPOOLED` | `DATABASE_URL_UNPOOLED` |
| `SECRET_KEY` | `SECRET_KEY` |
| `CLOUDINARY_CLOUD_NAME` | `CLOUDINARY_CLOUD_NAME` |
| `CLOUDINARY_API_KEY` | `CLOUDINARY_API_KEY` |
| `CLOUDINARY_API_SECRET` | `CLOUDINARY_API_SECRET` |

Plain env vars set at deploy: `ENVIRONMENT=production`, `CORS_ORIGINS`, `HSTS_ENABLED=true`, `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`.

## Neon project config (`neon.ts`)

Declares `auth: false` and a branch policy: the default branch gets no overrides; **new non-default branches get a 7-day TTL** (auto-expire); existing branches are untouched. Create such branches with `neon checkout <name>`.
