# Threat Model — InfyExchange

**Document type:** Threat model · **Version:** 1.1 · **Method:** STRIDE-informed, mapped to the
application as discovered (see HLD §1)

Assets: user accounts (email, phone, Argon2 hashes), JWT signing key, Cloudinary credentials,
listing/need content, contact data revealed after interest acceptance, admin audit logs,
availability of the API, PostgreSQL data.

## 1. Threat Table

| ID | Threat | Primary controls (implemented) | Status / residual risk |
|---|---|---|---|
| TH-01 | Unauthorized API access | JWT verification pinned to HS256; `get_current_user` on every protected route; 401/403 logging | Implemented |
| TH-02 | Broken object-level authorization | Ownership checks on every mutation; interview-contact gate; tests AUTHZ-001..004 | Implemented |
| TH-03 | SQL injection | ORM-only queries (no raw SQL in `app/`); injection probes in tests | Implemented |
| TH-04 | Credential theft | Argon2 hashing; per-IP + per-account login limits; identical failure messages; secrets outside git; no secrets in Vite vars | Implemented; MFA not implemented (see §3) |
| TH-05 | Direct origin bypass | API has no published port; only `web:80` public; Cloudflare proxy + OCI allowlist | Partially deployable — see runbook §3 (NET-004 to verify) |
| TH-06 | HTTP flood / DDoS | Cloudflare baseline; nginx `limit_req` 20 r/s burst 40, `limit_conn` 20; uvicorn `--limit-concurrency 200`; resource limits per container | Implemented at app/edge; volumetric protection depends on Cloudflare plan |
| TH-07 | Excessive API consumption | App-level limiters on auth/create/read/contact/admin with `Retry-After`; memory-bounded state | Implemented; per-process resets on restart (R-02) |
| TH-08 | Malicious file upload | Content-type allowlist, magic-byte verification, 5 MB streaming cap, 5 images max, Cloudinary storage (no local execution) | Implemented |
| TH-09 | Dependency compromise | Pinned requirements; dev toolchain; scan commands documented | Implemented; base images not digest-pinned (R-07); no CI yet |
| TH-10 | Database exposure | Postgres on `internal: true` network, no published port in prod; dev compose still maps 5432 on localhost (warning in LLD §8) | Implemented in prod compose |
| TH-11 | Host compromise | Non-root containers, `cap_drop`, `no-new-privileges`, read-only web FS | Host hardening (SSH, updates, UFW) is DEPLOY — runbook §2/§4 |
| TH-12 | Sensitive data in logs | Central UTC logging with request IDs; security events only; hashed account keys; generic client errors | Implemented |
| TH-13 | Backup theft | Encrypted backup procedure (age/gpg) with off-host storage; key stored separately | DEPLOY — runbook §7 |
| TH-14 | Cross-site scripting | React escaping; strict API CSP; SPA CSP report-only with explicit allowlist; no inline scripts in `index.html` | Implemented; CSP enforcement after burn-in (LLD §2.2) |
| TH-15 | CSRF | Header bearer tokens (not cookies) → not CSRF-exploitable today; no cookie auth exists | N/A now; required if cookies adopted (LLD §4) |
| TH-16 | Session theft | 7-day JWT; no revocation list; token in `localStorage` | Accepted residual risk R-01/R-03; mitigation CSP + XSS prevention |
| TH-17 | Cloud misconfiguration | Compose fails fast on missing secrets; internal network; documented Cloudflare/OCI checklist | Repo scope implemented; cloud settings DEPLOY |
| TH-18 | Service exhaustion | Body size limit (30 MB nginx), timeouts at nginx, uvicorn concurrency cap, container CPU/memory/pids limits, DB pool caps (config-driven — `db_pool_size` + `db_max_overflow` in `config.py`; do not restate the numbers here) | Implemented |
| TH-19 | DNS/certificate misconfiguration | HSTS gated; ACME path preserved; `server_tokens off` | DEPLOY verification (runbook §5) |
| TH-20 | Inadequate detection | `security` logger events, `audit_logs` table for admin actions, log rotation; alert procedure documented | Implemented partially; central alerting is DEPLOY (runbook §6) |

## 2. Attack Path Walkthroughs

**A. Credential stuffing.** Attacker sprays passwords. Per-IP limiter (10/min) throttles a
single source; the per-account SHA-256-keyed limiter (10/min) throttles distributed attacks on
one account. Failure responses are uniform. Cloudflare rate limiting adds an edge layer.
Gap: in-memory state is per worker (R-02) and resets on deploy; no CAPTCHA/MFA.

**B. Stolen token replay.** A token stolen from `localStorage` via XSS remains valid for up to
7 days; there is no revocation store (R-03). Mitigations: CSP, React escaping, short-lived
tokens via `ACCESS_TOKEN_EXPIRE_MINUTES`, deactivation still blocks the account on next request
(`is_active` check).

**C. Horizontal data access.** User B changes `/api/listings/{id}` to A's id. Every mutation
re-checks `owner_id`/`user_id`; contact data is gated on accepted-interest participation. Tests
AUTHZ-001..004 cover this path.

**D. Direct-to-origin bypass.** Attacker resolves the VM IP and calls port 80 directly,
bypassing Cloudflare WAF. Today mitigated only by Cloudflare proxy + rate limits at nginx.
Action: allowlist Cloudflare IP ranges in OCI NSG/UFW (runbook §3) and verify from an external
host (NET-004).

**E. Upload abuse.** Attacker posts a polyglot file. Content-type + magic bytes + 5 MB cap +
Cloudinary (no local execution, no local storage) limit impact. No AV scanning (R-08).

## 3. Residual Risk Register

| ID | Risk | Severity | Rationale / mitigation | Revisit trigger |
|---|---|---|---|---|
| R-01 | JWT in `localStorage` → XSS token theft | Medium | Contract preserved; CSP burn-in; React escaping | Any XSS report; CSP enforcement |
| R-02 | In-memory per-process rate limits | Medium | Bounded memory; multiple workers multiply limits | Scale-out or repeated abuse |
| R-03 | No token revocation / refresh flow | Medium | 7-day expiry; `is_active` gate | Add revocation store or shorten TTL |
| R-04 | Migrations run at app startup | Low | Intentional fail-fast deploy model; single API replica | Multi-replica rollout |
| R-05 | User enumeration via registration 409s | Low | UX decision; login responses are uniform | Abuse observed |
| R-06 | `--forwarded-allow-ips=*` trusts XFF if API reached directly | Low | API unpublished; verify origin restriction (NET-004) | Origin exposure |
| R-07 | Floating base image tags | Medium | Scans documented; rebuild cadence | CI addition |
| R-08 | No malware scanning of uploads | Low | Files never executed or hosted locally | Storage change |
| R-09 | No MFA / passkey | Medium | Free-tier scope; admin accounts recommended to use unique passwords | Feasibility review |
| R-10 | Cloudflare/OCI settings not verifiable from repo | High (until verified) | Full checklist in runbook §3/§5 | First deployment verification |
| R-11 | Admin audit trail covers mutations, not reads | Low | `audit_logs` on PATCH/DELETE only | Compliance need |

## 4. Verification Mapping

Each threat maps to test IDs in [TEST_PLAN.md](TEST_PLAN.md); automated coverage exists for
TH-01, TH-02, TH-03, TH-07, TH-12, TH-14 (headers), TH-18 (body/limits partially). Deployment
controls (TH-05, TH-10/13/19 host-side, TH-20 alerting) require the runbook procedures.
