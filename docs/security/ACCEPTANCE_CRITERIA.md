# Security Acceptance Criteria — Status

**Document type:** Acceptance criteria · **Version:** 1.1

Legend: **MET (repo)** = verified in the repository with evidence; **MET (deploy)** = verified on
the deployed stack (record evidence); **OPEN** = not yet satisfied.

## 1. Critical Requirements

| # | Criterion | Status | Evidence / action |
|---|---|---|---|
| C1 | PostgreSQL is not publicly reachable | MET (repo) + verify (deploy) | No published port; `internal: true` network (`docker-compose.prod.yml`). Verify NET-001/002 |
| C2 | Administrative access appropriately restricted | OPEN (deploy) | Procedure in runbook §3/§4; needs OCI NSG + UFW + SSH config evidence |
| C3 | No unintended management ports public | MET (repo) | Only `web:80` published; API/DB unpublished; Swagger disabled in production (`main.py`) |
| C4 | HTTPS valid for frontend and public API | OPEN (deploy) | Verify TLS-001/002/005; HSTS stays off until confirmed |
| C5 | Production secrets not in frontend assets | MET | Only `VITE_API_BASE_URL` is client-side; build-output grep documented (ASSET_INVENTORY §4) |
| C6 | Authentication enforced on protected endpoints | MET | Tests: `test_unauthenticated_access_denied`, `test_admin_endpoints_require_authentication`, `test_deactivated_user_rejected` |
| C7 | Authorization enforced server-side | MET | Ownership checks in routers; AUTHZ tests all PASS |
| C8 | User resources cannot be accessed across accounts | MET | `test_horizontal_escalation_*`, `test_contact_details_blocked_for_third_party` |
| C9 | SQL handles untrusted input safely | MET | ORM-only queries; injection-probe tests PASS; `bandit` 0 issues |
| C10 | DB credentials follow least privilege | OPEN (deploy) | Verify app role is not superuser (DB-001); compose uses a dedicated role |
| C11 | Sensitive errors not returned to clients | MET | Generic handlers (`main.py`); `test_errors_do_not_leak_internal_details`; no `password_hash` in responses |
| C12 | Backups protected and restore tested | OPEN (deploy) | Procedure in runbook §7 (encrypted, off-host, monthly restore drill); no backup exists yet |
| C13 | Security changes have documented rollback | MET | Runbook §8 table (per-change rollback) |

## 2. Additional Requirements

| # | Criterion | Status | Evidence / action |
|---|---|---|---|
| A1 | Cloudflare protections configured | OPEN (deploy) | Runbook §3/§5: proxy, SSL mode, rate rules, WAF managed rules (free tier) |
| A2 | Origin access follows trust model | OPEN (deploy) | Cloudflare IP allowlist procedure; NET-004 |
| A3 | API rate limits and resource limits configured | MET | App limiters + nginx `limit_req`/`limit_conn` + uvicorn concurrency + container limits; RATE tests PASS |
| A4 | Browser security headers evaluated/configured | MET | Middleware + nginx; CSP report-only with allowlist; WEB tests PASS |
| A5 | Secrets stored and rotated appropriately | MET (repo) + action | Not in git; `.env` perms/template documented; rotate local Cloudinary/SECRET_KEY per ASSET_INVENTORY action item |
| A6 | Security updates managed | OPEN (deploy) | Runbook §2 unattended-upgrades |
| A7 | Dependency scanning operational | MET (manual) | Pinned deps; `bandit` 0 issues; `pip-audit`/`npm audit`/`gitleaks` commands in runbook §8; **no CI** — schedule weekly cron at minimum |
| A8 | Security logs collected and access-restricted | PARTIAL | Structured `security` logger + rotation; central sink not yet configured (runbook §6) |
| A9 | Security events produce actionable alerts | OPEN (deploy) | Alert patterns listed in runbook §6; needs a sink |
| A10 | Incident response documented | MET | Runbook §10 quick card + rotation procedures |
| A11 | High-severity findings resolved/accepted | MET (repo) + DAST pending | Threat model register: no unaccepted High findings in repo scope; R-10 (cloud config unverified) accepted until first deploy verification. DAST-001..003 (ZAP) not yet executed |

## 3. Verification Snapshot (2026-10-21)

- Automated suite: **43/43 PASS** (`backend/tests`, SQLite isolation).
- `bandit -r backend/app`: **0 issues**.
- `docker compose -f docker-compose.prod.yml config`: **valid**; fails fast on missing secrets.
- nginx config syntax: **NOT RUN** (registry pull blocked in this environment) — run
  `docker run --rm -v "%cd%/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t`.
- `.env` exposure check: never tracked (`git log --all -- backend/.env` empty), only
  `.env.example` is tracked.

## 4. Sign-off Rule

The deployment must not be declared security-ready until **C1–C13 are all MET with evidence**.
Items C2, C4, C10, C12 and A1, A2, A6, A9 are deployment-side and remain OPEN by design of this
iteration (no cloud/host access from the repository). Each closed item should link to its
executed test ID from [TEST_PLAN.md](TEST_PLAN.md).
