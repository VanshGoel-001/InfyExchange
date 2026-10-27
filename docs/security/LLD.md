# Low-Level Design — Security Controls

**Document type:** LLD · **Version:** 1.1 · **Status:** Implemented (repository scope)

Every control below is implemented in the repository, with exact locations. Deployment-side
controls are marked **DEPLOY** and exist only as runbook procedures.

## 1. Network

### 1.1 Container network isolation — `docker-compose.prod.yml`

- `internal` network (`internal: true`) hosts `postgres` + `api`; it has **no route to the host**.
- `edge` network hosts `api` + `web`. Only `web` publishes a port (`80:80`).
- PostgreSQL publishes **no port** (previous dev compose still publishes 5432 — see §8).
- Outbound egress remains open for the `api` container (Cloudinary uploads). Restricting it is
  a **DEPLOY** decision (OCI NSG egress rules per destination: `api.cloudinary.com`,
  `res.cloudinary.com`).

### 1.2 Edge rate limiting — `nginx.conf`

```nginx
limit_req_zone $binary_remote_addr zone=api_rl:10m rate=20r/s;
limit_conn_zone $binary_remote_addr zone=api_conn:10m;
location /api/ { limit_req zone=api_rl burst=40 nodelay; limit_conn api_conn 20; ... }
```

Timeouts bound slow clients: `client_body_timeout 15s`, `client_header_timeout 15s`,
`send_timeout 30s`, `keepalive_timeout 30s`, `proxy_read_timeout 30s`,
`proxy_connect_timeout 10s`, `client_max_body_size 30m` (matches 5 images × 5 MB + multipart).

### 1.3 Origin protection — **DEPLOY**

Cloudflare-proxied DNS + OCI NSG allowlisting of `https://www.cloudflare.com/ips-*` ranges on
port 80/443; host UFW mirroring the NSG. Procedure: runbook §3. Not configurable from the repo.

## 2. Transport and Headers

### 2.1 Application security headers — `backend/app/middleware.py`

`SecurityHeadersMiddleware` sets on every response (does not overwrite existing values):

| Header | Value | Notes |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | |
| `X-Frame-Options` | `DENY` | |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | configurable `REFERRER_POLICY` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` | configurable |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` | API/JSON only; exempts `/docs`, `/redoc`, `/openapi.json` |
| `Cache-Control` | `no-store` | only on `/api/auth`, `/api/users/me`, `/api/interests`, `/api/admin` |
| `Strict-Transport-Security` | `max-age=<HSTS_MAX_AGE>[; includeSubDomains]` | **only when `HSTS_ENABLED=true`** |

`RequestContextMiddleware` assigns `X-Request-ID` (sanitized client value or UUID4) and binds it
to log records via `ContextVar`; nginx forwards its own `$request_id`.

### 2.2 SPA headers — `nginx.conf`

Adds the same headers at the edge plus:

- `Content-Security-Policy-Report-Only` with the verified allowlist:
  `script-src 'self'`, `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`
  (inline style attributes are used by React components), `font-src 'self' data:
  https://fonts.gstatic.com`, `img-src 'self' data: https://res.cloudinary.com`,
  `connect-src 'self'`, `frame-ancestors 'none'`.
- `server_tokens off`.
- `location ~ /\.` denies dotfiles; `location ^~ /.well-known/` is allowed for ACME.
- HSTS is commented out by design (enable per runbook §5 after HTTPS verification).

**Enforcement path for CSP:** run report-only in production for at least one release cycle,
confirm zero legitimate violations in browser consoles, then rename the header to
`Content-Security-Policy`. If the SPA is hosted on Cloudflare Pages and calls the API
cross-origin, add the API origin to `connect-src` first.

### 2.3 HSTS gate

`HSTS_ENABLED=false` by default everywhere. Enable only when: Cloudflare proxy is active, SSL
mode is Full (strict), and no subdomain is HTTP-only. Ramp `HSTS_MAX_AGE` 300 → 86400 → 604800 →
15552000. `HSTS_INCLUDE_SUBDOMAINS` stays `false` unless every subdomain is HTTPS.

### 2.4 Database transport

PostgreSQL is container-local (`postgres:5432` on the compose `internal` network). If the DB is
ever moved off-host, `DATABASE_URL` must carry `?sslmode=verify-full` (psycopg3 honors
`sslmode`) and `PGSSLROOTCERT` must point to a CA bundle. **DEPLOY** (host-level).

## 3. Authentication

- JWT HS256 via PyJWT; `algorithms=["HS256"]` pinned at decode (algorithm-confusion safe;
  covered by test `test_alg_none_token_rejected`).
- Passwords hashed with Argon2id (explicit `Argon2Hasher`, pinned so a `pwdlib` upgrade cannot
  change the algorithm; regression test asserts the `$argon2id$` prefix); verification is constant-time
  through the library.
- Login responses are identical for unknown email vs wrong password
  (`Invalid email or password`); covered by `test_login_failure_messages_are_identical`.
- Deactivated users are rejected on every authenticated request (`is_active` check); covered by
  `test_deactivated_user_rejected`.
- Password policy (`app/schemas/auth.py`): ≥ 8 chars, ≤ 100, at least one letter and one digit;
  `LoginRequest.password` is capped at 100 chars to bound hashing cost.
- Token lifetime remains `ACCESS_TOKEN_EXPIRE_MINUTES=10080` (7 days) to preserve the frontend
  contract; lowering it is a deployment knob (recommended: 1440 for admin-heavy sites).
  There is **no refresh-token flow and no revocation list** (residual risk R-03).

## 4. Token storage trade-off (documented threat assessment)

The frontend stores the bearer token in `localStorage('infy_token')` (`src/services/api.js`,
`src/context/AuthContext.jsx`). This was **kept** to avoid breaking the API contract.

- Exposure: any XSS payload can read the token; therefore XSS prevention is the primary control
  (CSP report-only → enforcing, React escaping, no `dangerouslySetInnerHTML` usage).
- CSRF: not applicable to header-borne bearer tokens; cookies would introduce CSRF duties.
- Migration path (future): HttpOnly + `Secure` + `SameSite=Lax` cookie set by `/api/auth/login`,
  CSRF double-submit token for state-changing routes, `credentials: 'include'` in the client.
  This is an API-contract change and is out of scope for the incremental hardening.

## 5. Authorization

- Router-level dependency `get_current_admin` on `/api/admin/*`; every mutation checks resource
  ownership before acting (`listings.py` update/delete, `needs.py` delete,
  `interests.py` accept/reject/contact).
- `GET /api/interests/{id}/contact` reveals contact data only to the two participants and only
  after `ACCEPTED` (`interests.py` lines ~320-348).
- Covered by `tests/test_authorization.py` (horizontal/vertical escalation, third-party access).

## 6. Input Validation and Data Access

- All write payloads are Pydantic models with length/range/enum constraints; multipart form
  fields carry explicit `Form(...)` constraints.
- Queries use SQLAlchemy ORM expressions only; no string-built SQL anywhere in `app/`.
- Error handlers (`app/main.py`) map validation errors to flattened 422 details and mask
  `SQLAlchemyError`/unexpected exceptions behind generic messages; full detail goes to logs only.
- Response models exclude `password_hash` (`UserResponse`); covered by tests.
- Upload validation: content-type allowlist, magic-byte check, 5 MB streaming cap, 5 images per
  listing (`app/services/cloudinary.py`, `app/routers/listings.py`).

## 7. Rate Limiting — `app/services/rate_limit.py`

Sliding-window, in-memory, **per worker process** (documented limitation R-02). All limits are
settings-driven (`RATE_LIMIT_*`, default 60 s window):

| Limiter | Default | Applied at |
|---|---|---|
| login (per IP) | 10 / min | `POST /api/auth/login` |
| login-account (per hashed email) | 10 / min | `POST /api/auth/login` |
| register (per IP) | 5 / min | `POST /api/auth/register` |
| create (per IP) | 10 / min | `POST /api/listings`, `/api/needs`, `/api/interests/listing/{id}` |
| read (per IP) | 120 / min | `GET /api/listings`, `/api/needs` |
| contact (per IP) | 20 / min | `GET /api/interests/{id}/contact` |
| admin (per IP) | 60 / min | router-level on `/api/admin/*` |

- Rejections are HTTP 429 with `Retry-After: <window>` and a `security` log line.
- Keying uses `request.client.host`, resolved by uvicorn `--proxy-headers` from nginx's
  `X-Real-IP`/`X-Forwarded-For`. Because uvicorn is started with `--forwarded-allow-ips=*`, an
  attacker who can reach the API directly can spoof the header — the API has no published port
  and should only be reachable via nginx and Cloudflare (deployment check NET-004). Residual
  risk R-06.
- Memory safety: expired keys are pruned once per window and the key count is capped at
  `MAX_TRACKED_KEYS = 10_000` with oldest-key eviction; covered by unit tests.

## 8. Dev Compose Warning — `backend/docker-compose.yml`

The **development** compose still publishes `5432:5432` with `postgres/postgres`. It is not used
in production, but it is a foot-gun on shared networks: run it only on a trusted machine or
change it to bind `127.0.0.1:5432:5432`. Not modified here to avoid breaking local workflows.

## 9. Logging and Monitoring

- `app/utils/logging_utils.py`: single root handler, UTC ISO-8601 timestamps,
  `request_id` injection, `security` logger namespace.
- Events emitted: `auth_failed`, `login_failed`, `deactivated_account_access`,
  `admin_access_denied`, `rate_limit_exceeded`, `service_started`, `service_stopped`.
- No passwords, tokens, raw emails (login-account keys are SHA-256 truncated hashes), or
  personal data are logged; IPs and user IDs are logged for investigation.
- Docker log rotation: `json-file`, `max-size: 10m`, `max-file: 3` per service (disk exhaustion
  guard).
- **DEPLOY:** ship stdout to a central sink (OCI Logging free tier or journald), alert on
  `security` log patterns — runbook §6.

## 10. Supply Chain

- `backend/requirements.txt` pins exact versions (verified against the running environment:
  fastapi 0.142.2, sqlalchemy 2.1.2, pydantic 2.13.5, pyjwt 2.15.1, cloudinary 1.46.2, …).
- `backend/requirements-dev.txt`: pytest 9.1.1, httpx 0.28.1, pytest-cov 7.1.0, bandit 1.9.4.
- CI/scan commands (runbook §8): `pip-audit`, `bandit -r app`, `npm audit`,
  `gitleaks detect`, `trivy fs`.
- Docker base images are floating tags (`python:3.12-slim`, `postgres:17-alpine`,
  `nginx:alpine`). Pinning digests is recommended (residual risk R-07).

## 11. Changed Code Reference

| File | Change |
|---|---|
| `backend/app/middleware.py` | New: security headers, request-ID correlation, no-store rules |
| `backend/app/utils/logging_utils.py` | New: UTC logging, security logger, request-ID filter |
| `backend/app/config.py` | New settings: headers, HSTS gate, ALLOWED_HOSTS, rate limits |
| `backend/app/services/rate_limit.py` | Settings-driven limiters, `enforce()` with Retry-After, pruning, `rate_limit_dependency`, `account_key` |
| `backend/app/main.py` | Logging setup, lifespan log events, CORS method/header allowlists, opt-in `TrustedHostMiddleware`, middleware registration |
| `backend/app/dependencies.py` | Security logging on 401/403 paths |
| `backend/app/routers/auth.py` | `enforce()` usage, per-account login limiter, `login_failed` log |
| `backend/app/routers/{listings,needs,interests,admin}.py` | Rate limiter wiring |
| `backend/app/schemas/auth.py` | Password strength validator; login password length cap |
| `backend/Dockerfile` | `--limit-concurrency 200`, `--timeout-keep-alive 30` |
| `nginx.conf` | CSP report-only, Permissions-Policy, rate/conn limits, timeouts, dotfile deny, `server_tokens off`, `X-Request-ID` pass-through |
| `docker-compose.prod.yml` | Required secrets fail-fast, internal network, resource/pids limits, `no-new-privileges`, `cap_drop`, `read_only` + tmpfs for web, log rotation |
| `backend/requirements.txt`, `backend/requirements-dev.txt` | Pinning; dev/test toolchain |
| `backend/.env.example`, `.env.prod.example` | Documented security knobs |
