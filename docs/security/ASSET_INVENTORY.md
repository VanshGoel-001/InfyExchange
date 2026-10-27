# Asset Inventory

**Document type:** Asset inventory · **Version:** 1.1

No secret values are listed here. Items marked **UNKNOWN** must be discovered on the deployment
(see runbook §0).

## 1. Applications and Services

| Asset | Version / image | Location | Exposure |
|---|---|---|---|
| Frontend SPA | React 19.3, Vite 8.3, react-router 7.18 (lockfile `package-lock.json`) | `src/` → `dist/` | Public static (Cloudflare Pages `<FRONTEND_DOMAIN>`; also served by nginx `/`) |
| API | FastAPI 0.142.2, Uvicorn 0.54.0, Python 3.12-slim | `backend/` | Public via `web` → `/api/*` only |
| Web tier | nginx:alpine | `nginx.conf` | Public port 80 (host) |
| Database | PostgreSQL 17-alpine | compose volume `postgres_data` | Internal compose network only |
| Media store | Cloudinary (`infyexchange/listings/...`) | external SaaS | Public URLs (listing images) |
| Host | Oracle Cloud VM `<OCI_VM_SHAPE>`, `<OCI_REGION>`, OS `<OCI_VM_OS>` | OCI | **UNKNOWN** until discovered |

## 2. Network Endpoints

| Endpoint | Port | Reachable from | Notes |
|---|---|---|---|
| `<API_DOMAIN>` / `<FRONTEND_DOMAIN>` | 443 | Internet (via Cloudflare) | TLS at edge |
| `<ORIGIN_IP>` | 80 | Should be Cloudflare ranges only | nginx; NET-004 verifies |
| `<ORIGIN_IP>` | `<ADMIN_SSH_PORT>` | `<ADMIN_IP>` only | SSH keys, no root login |
| `api:8000` | 8000 | compose `edge` network | Not published to host |
| `postgres:5432` | 5432 | compose `internal` network | Not published; `internal: true` |
| Dev compose `backend/docker-compose.yml` | 5432 | Host localhost | **Dev only** — do not run on untrusted hosts |

## 3. Data Assets

| Asset | Classification | Location | Protection |
|---|---|---|---|
| User accounts (name, email, phone, role) | PII | PostgreSQL | DB auth, network isolation, backups encrypted |
| Password hashes (Argon2) | Secret-adjacent | PostgreSQL | Never returned by API; verified by tests |
| Listings / needs / interests | Business data | PostgreSQL | Owner-scoped mutations |
| Contact details (post-acceptance reveal) | PII | API responses | Participant-gated; rate-limited |
| Listing images | Business data | Cloudinary | Server-side credentials only |
| Admin audit log (`audit_logs`) | Sensitive operational | PostgreSQL | Admin-only endpoint |
| Backups | PII | Off-host, encrypted (`age`) | Key stored off-VM (runbook §7) |

## 4. Secrets Inventory

| Secret | Used by | Storage (verified) | Rotation |
|---|---|---|---|
| `SECRET_KEY` (JWT HS256) | API | Local `backend/.env` (dev) and root `.env` (prod); **never committed** (`git log --all -- backend/.env` empty) | Quarterly or on suspicion; invalidates all tokens |
| `POSTGRES_PASSWORD` | API, Postgres | same `.env` files | Quarterly via `ALTER USER` + `.env` + restart |
| `CLOUDINARY_API_KEY` / `_SECRET` / `CLOUD_NAME` | API only (server-side SDK) | same `.env` files | Quarterly or on suspicion; Cloudinary console |
| Cloudflare API tokens (if any) | Operator | **UNKNOWN** — operator-held | Per provider policy |
| OCI API keys | Operator | **UNKNOWN** | Per provider policy |
| Backup encryption key (`age`) | Operator | **Off the VM** | Yearly |

Client-side exposure audit: the only Vite variable is `VITE_API_BASE_URL` (non-secret, defaults
to `/api`). No server credentials are compiled into `dist/`. Re-verify after every frontend
dependency change: `npm run build` then `grep -R "CLOUDINARY\|SECRET_KEY" dist/` (expect none).

> Action item: the local `backend/.env` contains live Cloudinary credentials and the JWT key.
> They were never committed, but rotate them as a precaution if this machine or any copy of it
> has been shared (runbook §10).

## 5. Software Supply Chain

| Ecosystem | Lock mechanism | Scan command |
|---|---|---|
| Python | `backend/requirements.txt` pinned (fastapi 0.142.2, sqlalchemy 2.1.2, pydantic 2.13.5, pyjwt 2.15.1, psycopg 3.3.6, cloudinary 1.46.2, alembic 1.20.0, uvicorn 0.54.0, pwdlib 0.3.1, python-multipart 0.0.32, email-validator 2.3.0, python-dotenv 1.2.4, pydantic-settings 2.15.0) | `pip-audit -r backend/requirements.txt`, `bandit -r backend/app` |
| Node | `package-lock.json` committed | `npm audit --production`, `npm ci` in CI |
| Containers | `python:3.12-slim`, `postgres:17-alpine`, `nginx:alpine` (floating tags) | `trivy image <img>` (recommended: pin digests) |
| Secrets | none in git history | `gitleaks detect --source .` |

## 6. Accounts and Access Paths

| Account | Where | Purpose | Notes |
|---|---|---|---|
| `appuser` (uid non-root) | API container | Runs uvicorn | No shell capability needed |
| `<SSH_USER>` | VM | Administration | Key-only; sudo per policy |
| Postgres app role (`POSTGRES_USER`) | DB | Runtime queries + owner of schema | Must **not** be superuser in long-term design (verify DB-001) |
| Cloudinary API key | Cloudinary | Image upload/destroy | Server-side only |

## 7. Monitoring Assets (current)

| Asset | State |
|---|---|
| Application `security` logger (stdout) | Implemented |
| Admin audit log table | Implemented |
| DAST (OWASP ZAP, `scripts/security/zap-api-scan.ps1`) | Scripted; **not yet executed** (needs image pull + running target) |
| Docker log rotation | Implemented (10 MB × 3) |
| Central log sink / alert delivery | **Not implemented** — runbook §6 |
| Host IDS / AV / NIDS | **Not installed** — evaluate per runbook §9 |
