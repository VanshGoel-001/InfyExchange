# Security Test Plan and Execution Record

**Document type:** Test plan · **Version:** 1.1

## 1. Environments and Rules

1. Automated suite — runs locally against an isolated SQLite database (no production data).
2. Staging/isolated deployment — full stack verification.
3. Production — only non-destructive configuration verification and smoke tests.

Never run load, fuzzing, or volumetric tests against production. Use synthetic accounts. Do not
mark a test PASS without evidence.

## 2. Automated Suite

Location: `backend/tests/` (pytest). Run:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m bandit -r app -q
```

Setup (fresh machine): `python -m venv .venv`;
`.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.

### Execution record — 2026-10-21 (local, SQLite isolation)

| Field | Value |
|---|---|
| Command | `.venv\Scripts\python.exe -m pytest -q` |
| Result | **43 passed, 0 failed** (10.4 s) |
| Static analysis | `bandit -r app` → **0 issues** (B105 `"bearer"` literal suppressed with justification and comment) |
| Compose validation | `docker compose -f docker-compose.prod.yml config` → **valid** (exit 0; fails fast when required vars are absent — verified) |
| nginx syntax | **BLOCKED** — container image pull failed in this environment; run `docker run --rm -v "%cd%/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t` before deploy |

### Automated case map

| Test | Requirement | Expected | Status |
|---|---|---|---|
| `test_security_headers_present` | WEB-002 | nosniff, DENY, referrer, permissions, CSP on all API responses | PASS |
| `test_hsts_absent_when_disabled` | WEB-002/TLS | No HSTS until enabled | PASS |
| `test_hsts_present_when_enabled` | WEB-002 | `max-age` matches config when enabled | PASS |
| `test_csp_exempts_docs_paths` | WEB-003 | `/openapi.json` not blocked by API CSP | PASS |
| `test_request_id_is_returned` / `..._malformed` | OBS | Request ID present; malformed input not echoed | PASS |
| `test_cors_allows_configured_origin` | WEB-001 | Allowlisted origin allowed | PASS |
| `test_cors_blocks_unknown_origin_preflight` | WEB-001 | Unknown origin gets no CORS grant | PASS |
| `test_cors_rejects_wildcard_with_credentials` | WEB-001 | No `*` origin with credentials | PASS |
| `test_sensitive_endpoints_not_cached` | DATA | `Cache-Control: no-store` on auth responses | PASS |
| `test_unauthenticated_access_denied` | AUTH-001 | 401/403 without credentials | PASS |
| `test_invalid_token_rejected` | AUTH-002 | 401 on garbage token | PASS |
| `test_alg_none_token_rejected` | AUTH-002 | Forged `alg=none` JWT rejected | PASS |
| `test_deactivated_user_rejected` | AUTH-003 | 403 for deactivated account | PASS |
| `test_login_failure_messages_are_identical` | AUTH-002 | Uniform failure detail | PASS |
| `test_login_success_returns_bearer_token` | AUTH-001 | 200 + bearer token | PASS |
| `test_password_policy_*` (3 tests) | AUTH-004 | Strength rules enforced, strong password accepted | PASS |
| `test_registration_rejects_disallowed_email_domain` | INPUT-001 | 400 for non-allowlisted domain | PASS |
| `test_login_rate_limit_returns_429_with_retry_after` | RATE-001 | 429 + `Retry-After` after threshold | PASS |
| `test_registration_rate_limit_returns_429` | RATE-001 | 429 after threshold | PASS |
| `test_cannot_read_other_users_profile_endpoint` | AUTHZ-003 | `/users/me` resolves token identity only | PASS |
| `test_horizontal_escalation_listing_update_blocked` | AUTHZ-001 | 403 cross-user update | PASS |
| `test_horizontal_escalation_listing_delete_blocked` | AUTHZ-001 | 403 cross-user delete | PASS |
| `test_owner_can_update_own_listing` | AUTHZ-004 | Owner update allowed (no false negatives) | PASS |
| `test_vertical_escalation_admin_stats_blocked` | AUTHZ-002 | 403 for non-admin | PASS |
| `test_admin_endpoints_require_authentication` | AUTH-001 | 401/403 anonymous admin access | PASS |
| `test_admin_can_access_admin_stats` | AUTHZ-004 | Admin allowed | PASS |
| `test_cannot_show_interest_in_own_listing` | INPUT | 400 self-interest | PASS |
| `test_contact_details_blocked_before_acceptance` | AUTHZ-003 | 403 before acceptance | PASS |
| `test_contact_details_blocked_for_third_party` | AUTHZ-003 | 403 for outsider after acceptance | PASS |
| `test_contact_details_visible_to_participants` | AUTHZ-004 | Both participants see each other's contact | PASS |
| `test_register_rejects_missing_fields` / `..._oversized_values` | INPUT-001 | 422 on bad schema | PASS |
| `test_search_input_cannot_break_sql` / `..._quotes_returns_cleanly` | INPUT-003 | Injection probes return 200, no SQL errors | PASS |
| `test_registration_response_has_no_password_hash` | DB-003 | No hash in responses | PASS |
| `test_profile_response_has_no_password_hash` | DB-003 | No hash in responses | PASS |
| `test_errors_do_not_leak_internal_details` | INPUT-004 | No traceback/SQLAlchemy text | PASS |
| `test_rate_limiter_bounds_memory_under_key_rotation` | RATE-002 | Key store bounded at 10 000 | PASS |
| `test_rate_limiter_window_expiry` | RATE-002 | Limit recovers after window | PASS |

## 3. Deployment Verification Cases

Run in staging first; production only for read-only/config checks. Record evidence (redacted
command output) — do not paste secrets.

### A. Network and Firewall (production, read-only where possible)

| ID | Procedure | Expected |
|---|---|---|
| NET-001 | From an external host: `nc -zv <ORIGIN_IP> 5432` | Connection refused/timeout |
| NET-002 | `docker compose -f docker-compose.prod.yml ps --format json` on the VM; external scan of <ORIGIN_IP> | Only `80/tcp` (and admin SSH) open; no `8000`, no `5432` published |
| NET-003 | SSH from authorized IP; SSH from an unauthorized source | Authorized works; unauthorized times out |
| NET-004 | `curl -H "Host: <API_DOMAIN>" http://<ORIGIN_IP>/api/health` from an external host | Blocked after Cloudflare allowlist (expected 403/timeout from OCI NSG) |

### B. TLS and Headers

| ID | Procedure | Expected |
|---|---|---|
| TLS-001/002 | `curl -sv https://<FRONTEND_DOMAIN>` and `https://<API_DOMAIN>/health` | Valid certificate; HTTP/2; no mixed content in browser console |
| TLS-003 | `curl -I http://<API_DOMAIN>` | 301/308 to HTTPS (Cloudflare edge) |
| TLS-005 | `openssl s_client -connect <API_DOMAIN>:443 -servername <API_DOMAIN>` | Valid chain, modern TLS |
| WEB-002 | `curl -sI https://<API_DOMAIN>/health` | nosniff, DENY frame, referrer, permissions, CSP, X-Request-ID |
| WEB-003 | Load SPA, open devtools console, exercise login/upload/search | Zero CSP violations in report-only mode |
| WEB-001 | `curl -sI -X OPTIONS -H "Origin: https://evil.example" .../api/listings` | No `access-control-allow-origin` for unknown origin |

### C. Auth/AuthZ on the deployed stack

| ID | Procedure | Expected |
|---|---|---|
| AUTH-001 | `curl https://<API_DOMAIN>/api/users/me` | 401/403 |
| AUTH-004 | 11 rapid failed logins | 429 with `Retry-After` |
| AUTHZ-001 | Two synthetic accounts; A calls PUT/DELETE on B's listing id | 403 |
| AUTHZ-004 | Admin API called with a normal user's token | 403 |

### D. Availability and Size Limits

| ID | Procedure | Expected |
|---|---|---|
| RATE-002 | Controlled burst beyond nginx `limit_req` in staging only | 503/429 from nginx; API stays responsive |
| RATE-003 | POST > 30 MB body | 413 from nginx before API work |
| RATE-004 | Slow body upload (`curl --limit-rate 1k`) | Closed after `client_body_timeout` |

### E. Database and Backups

| ID | Procedure | Expected |
|---|---|---|
| DB-001 | `\du` via `docker compose exec postgres psql` | App role is not superuser |
| DB-002 | Connect to 5432 from another host on the VM network | Refused (no published port) |
| DB-004/005, REC-001..003 | Follow runbook §7: create encrypted backup, restore into a scratch container, run `alembic current` + row counts | Restore succeeds; RPO/RTO met |

### F. Host

| ID | Procedure | Expected |
|---|---|---|
| HOST-001 | `sudo apt list --upgradable` (or distro equivalent) | Security updates per policy (runbook §2) |
| HOST-002 | `sshd -T` (filter `permitrootlogin` / `passwordauthentication`) | `no` / `no` |
| HOST-004 | Failed SSH login from test host; check journal/`security` logs | Event recorded; alert path exercised |
| HOST-005 | `sudo reboot` in maintenance window; then `sudo ufw status` and `docker compose ps` | Firewall rules and stack restored |

### G. Supply Chain

| ID | Procedure | Expected |
|---|---|---|
| SUPPLY-001 | `pip-audit -r backend/requirements.txt`; `npm audit --production` | Findings triaged and assigned |
| SUPPLY-002 | `gitleaks detect --source .` | No active secrets in commits (`.env` was never committed — verified `git log --all -- backend/.env`) |
| SUPPLY-004 | `docker compose build api`; `npm run build` | Builds succeed with pinned deps |

### H. Dynamic scanning (DAST — OWASP ZAP)

ZAP runs from Docker via `scripts/security/zap-api-scan.ps1` and is complementary to, not a
replacement for, the authorization suite in §2. Run against staging; production disables
`/openapi.json` on purpose.

| ID | Procedure | Expected |
|---|---|---|
| DAST-001 | `powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1` with the API started with `ENVIRONMENT=test` | Scan completes; every FAIL alert triaged; no High finding without a THREAT_MODEL register entry |
| DAST-002 | `powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1 -Mode baseline -Target http://host.docker.internal:5173` | No missing-header or information-disclosure failures on the SPA |
| DAST-003 | Authenticated coverage with `-ContextFile` injecting `Authorization: Bearer <token>` | Owner-scoped endpoints exercised without 5xx; other users still get 401/403 |

Execution status: **NOT RUN** — the target must be running and the `ghcr.io/zaproxy/zaproxy:stable`
image pulled; registry pulls failed in the implementation environment. Requirements are recorded
so the scan is repeatable, not claimed as evidence.

## 4. Open Items

- nginx `-t` syntax check (blocked here; run before deploy).
- OWASP ZAP scans DAST-001..003 (blocked here; Docker image pull required). Reports land in
  `zap-reports/` (gitignored).
- All `DEPLOY` cases above require cloud/host access and are not yet executed.
- CSP enforcement (rename report-only header) pending one burn-in cycle.
