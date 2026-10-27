# High-Level Design — InfyExchange Security Architecture

**Document type:** HLD · **Version:** 1.1 · **Status:** Implemented (repository scope)

This HLD reflects the **discovered** deployment, not an assumed one. Values that could not be
verified from the repository are written as placeholders in angle brackets and are listed in
[ASSET_INVENTORY.md](ASSET_INVENTORY.md) as "must be discovered".

## 1. Discovered Architecture

| Component | Discovered technology | Evidence |
|---|---|---|
| Frontend | React 19.3 + Vite 8.3 (single-page app), built to `dist/`; lockfile committed | `src/`, `vite.config.js`, `package.json`, `package-lock.json` |
| Frontend hosting (target) | Cloudflare Pages (`<FRONTEND_DOMAIN>` to confirm) | spec target; exact domain unknown |
| Edge network | Cloudflare proxy/DNS for the API host (`<API_DOMAIN>` to confirm) | target architecture |
| Web tier | `nginx:alpine`, serves `dist/` + proxies `/api/*` | `nginx.conf`, `docker-compose.prod.yml` |
| API | FastAPI 0.142.2 on Uvicorn 0.54.0, Python 3.12 image | `backend/Dockerfile`, `backend/requirements.txt` |
| AuthN | JWT HS256 (PyJWT), 7-day access tokens, Argon2id password hashing (pwdlib) | `app/services/auth.py` |
| Database | PostgreSQL 17 (alpine), no published port in prod compose | `docker-compose.prod.yml` |
| ORM / migrations | SQLAlchemy 2.1.2 + Alembic (migrations applied at app startup) | `app/services/migration.py` |
| Media | Cloudinary (server-side credentials only) | `app/services/cloudinary.py` |
| Host OS | Oracle Cloud VM — OS/version **must be discovered** (`<OCI_VM_OS>`) | spec |
| Logging | stdout JSON-less structured text, UTC, request IDs | `app/utils/logging_utils.py` |

### Request flow

```
Browser ──HTTPS──► Cloudflare edge (DNS, TLS, DDoS)
   │                    │
   │                    ├──► Cloudflare Pages (static SPA)
   │                    └──► <API_DOMAIN> → Oracle VM → nginx :80
   │                                               ├─ /        → dist/ (SPA)
   │                                               └─ /api/*   → api:8000 (FastAPI)
   │                                                                  │
   │                                                                  └─► postgres:5432
   │                                                                      (internal network only)
```

### Container topology (`docker-compose.prod.yml`)

| Service | Published ports | Networks | Privileges |
|---|---|---|---|
| `web` (nginx) | `80` (only public port) | `edge` | `cap_drop: ALL` + 5 minimal caps, `read_only`, `no-new-privileges` |
| `api` (uvicorn) | none | `edge`, `internal` | non-root `appuser`, `cap_drop: ALL`, `no-new-privileges` |
| `postgres` | none | `internal` (`internal: true`) | `no-new-privileges` |

No service other than `web` exposes a port to the host. PostgreSQL is unreachable from outside
the compose project.

## 2. Trust Boundaries (as implemented)

| ID | Boundary | Implemented controls | Deployment-side controls (verify) |
|---|---|---|---|
| TB-01 | Browser → Cloudflare | HTTPS enforced at edge; app sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP (report-only for SPA), HSTS (gated) | Cloudflare SSL mode Full (strict) recommended |
| TB-02 | Cloudflare → origin | Origin port 80 is the only ingress; app rejects nothing by cloud IP today (not verifiable from repo) | Cloudflare IP allowlist on OCI NSG/UFW, Authenticated Origin Pulls — see runbook |
| TB-03 | nginx → API | API container has no published port; only `web` reaches `api:8000` over the `edge` network | — |
| TB-04 | API → PostgreSQL | DB on `internal: true` network, no published port, single app role | `pg_hba.conf` review on host |
| TB-05 | Admin → VM | SSH over key auth (confirm on host) | OCI NSG restricted to admin IP; UFW; no root login — see runbook |
| TB-06 | API → Internet | Cloudinary uploads require egress; no egress restriction implemented (documented residual risk) | Optional OCI egress rules |

## 3. Security Design Principles Applied

- **Defense in depth:** headers at both nginx and FastAPI; rate limits at nginx (`limit_req`) and
  in the app (`InMemoryRateLimiter`); network isolation plus DB auth.
- **Least privilege:** non-root API user, `cap_drop: ALL`, DB account is the app role only
  (never postgres superuser — confirm on host).
- **Secure defaults:** production compose **fails fast** when `SECRET_KEY`,
  `POSTGRES_PASSWORD`, `CORS_ORIGINS`, or Cloudinary credentials are missing; no weak fallback
  password exists anymore.
- **Deny-by-default network:** Postgres on internal network; only `web:80` is published.
- **Fail-safe errors:** validation, SQLAlchemy, and unhandled exceptions return generic JSON
  without stack traces or SQL details (`app/main.py` handlers).
- **Auditability:** admin mutations write to `audit_logs` (actor, action, target, IP, details);
  auth failures, rate-limit hits, and admin denials are logged to the `security` logger with
  request correlation IDs.
- **Recoverability:** documented backup/restore procedure with encryption (runbook §7).

## 4. Threat Model Summary

Full table in [THREAT_MODEL.md](THREAT_MODEL.md). Residual risks (accepted, documented):
JWT in `localStorage` (XSS exposure with CSP mitigation), per-process in-memory rate limiting,
migrations executed at application startup, and lack of token revocation.

## 5. Change Surface of This Iteration

| Area | Files |
|---|---|
| App middleware (headers, request IDs, no-store) | `backend/app/middleware.py` (new) |
| Central logging (UTC, request IDs, security logger) | `backend/app/utils/logging_utils.py` (new) |
| Rate limiting (configurable, `Retry-After`, memory-bounded) | `backend/app/services/rate_limit.py`, routers `auth/listings/needs/interests/admin` |
| AuthN/AuthZ logging + password policy | `backend/app/dependencies.py`, `backend/app/routers/auth.py`, `backend/app/schemas/auth.py` |
| CORS tightening + opt-in Host validation | `backend/app/main.py`, `backend/app/config.py` |
| Edge hardening | `nginx.conf` |
| Runtime hardening | `docker-compose.prod.yml`, `backend/Dockerfile` |
| Supply chain | `backend/requirements.txt` (pinned), `backend/requirements-dev.txt` (new) |
| Tests | `backend/tests/` (new), `backend/pytest.ini` (new) |
| Config templates | `backend/.env.example`, `.env.prod.example` (new) |

## 6. What This Iteration Does Not Do

- Does not modify Cloudflare, Oracle Cloud NSG, or the host OS (no access from the repository);
  these are covered as explicit runbook procedures with placeholders.
- Does not migrate tokens from `localStorage` to HttpOnly cookies (would break the existing
  API contract; documented trade-off and migration path in LLD §4).
- Does not add Wazuh/ClamAV/Suricata (resource-bound; evaluation criteria in runbook §9).
