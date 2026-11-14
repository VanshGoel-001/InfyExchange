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
| `GOOGLE_CLIENT_ID` | empty | OAuth client ID of the Google Sign-In web client (public, not a secret). Empty switches "Sign in with Google" off (`POST /auth/google` answers `503`). Set it from the `GOOGLE_CLIENT_ID` GitHub variable: the deploy writes this one on every run (an empty GitHub variable blanks it), while other variables set by hand on the service are left alone (`--update-env-vars`) |
| `ALLOWED_HOSTS` | empty | If non-empty, enables `TrustedHostMiddleware` with this comma-separated list |

### Marketplace policy

| Variable | Default | Notes |
| --- | --- | --- |
| `LISTING_EXPIRY_DAYS` | 30 | Used for both listings and needs |
| `MAX_IMAGES_PER_LISTING` | 5 | Mirror in `PostingPage.jsx` |
| `MAX_IMAGE_SIZE_MB` | 5 | Mirror in `PostingPage.jsx` |
| `DUPLICATE_SUBMISSION_WINDOW_SECONDS` | 60 | Idempotency window for creating listings/needs |

### Email

Provider-agnostic: routes queue a background task; `services/email_service.py` picks an adapter. Templates are in `app/templates/email/`.

| Variable | Default | Notes |
| --- | --- | --- |
| `EMAIL_PROVIDER` | `console` | `console` prints the recipient, subject and a body preview to the log (local dev, or no account yet). `brevo` sends through Brevo's HTTPS API (`https://api.brevo.com/v3/smtp/email`, port 443). Any other value stops the app at startup |
| `EMAIL_API_KEY` | empty | Brevo API key. A secret: Secret Manager in production, never the SPA |
| `SENDER_EMAIL` | empty | Must be a sender verified in Brevo. With `brevo` selected, a missing key or sender logs a warning and falls back to the console adapter |
| `ADMIN_EMAIL` | empty | Receives an alert for every enquiry (reply-to is the enquirer). Empty: a warning is logged and no alert is sent |

Only two emails exist: a welcome email after registration, and the admin alert for a new enquiry. A failed send raises, is logged with a traceback and is stored in `failed_emails` for an admin to retry or discard. **These variables are not yet wired into `.github/workflows/cloud-run-deploy.yml`**, so production stays on the console adapter until they are added.

### Enquiry timing

| Variable | Default | Notes |
| --- | --- | --- |
| `PENDING_ENQUIRY_EXPIRY_DAYS` | 7 | A pending enquiry nobody answered closes after this long; the buyer is told |
| `CHAT_INACTIVITY_REMINDER_HOURS` | 48 | A chat with no activity this long gets one reminder to the owner |
| `MAINTENANCE_INTERVAL_SECONDS` | 3600 | How often the in-process job runs (see Known Limitations on scheduling) |

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
| `RATE_LIMIT_CHAT` | 30 (per signed-in user) |
| `RATE_LIMIT_ACTION` | 30 (per signed-in user) |
| `RATE_LIMIT_POLL` | 90 (per signed-in user) |

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

**The deploy workflow no longer sets these** (it used `--set-secrets` until now). They are managed by hand on the Cloud Run service; the owner reports they are currently plain environment variables there (not verified from this repository). The table is the Secret Manager layout the project was designed for and the intended hardening if you move them:

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
