# Testing

> A spec-derived test plan with requirement/acceptance-criteria/task mapping, manual scenarios and open questions is in [test.md](../test.md). The inventory below describes the original four files; `test.md` covers the newer `test_service_*`, `test_api_*`, `test_validation_schemas.py` and `test_data_integrity.py` files.

## What exists

| Layer | Tooling | Status |
| --- | --- | --- |
| Backend API | `pytest` + FastAPI `TestClient` (`httpx`) | **578 tests passed** (last full run: 2026-11-13, ~3.5 min), in 18 files: the original 4 plus the spec-derived suite described in [test.md](../test.md), plus Google sign-in and profile tests |
| Backend static analysis | Bandit, CodeQL | CI |
| Dependency vulnerabilities | `pip-audit`, `npm audit`, dependency-review | CI |
| Frontend | – | No unit, component or end-to-end tests; CI only builds and audits |
| Dynamic security scan | OWASP ZAP via `scripts/security/zap-api-scan.ps1` | Manual, staging only |
| Contract drift | `scripts/security/openapi_diff.py` | Manual |

## Running the backend tests

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m pytest -q                 # all tests
python -m pytest tests/test_auth.py -q
python -m pytest -k rate_limit -q
```

`pytest.ini` sets `testpaths = tests` and ignores `DeprecationWarning`. `pytest-cov` is installed if you want coverage (`python -m pytest --cov=app`).

## How the test harness works (`tests/conftest.py`)

1. **Environment first.** Before importing any app module, the file sets `DATABASE_URL` (a SQLite file in the OS temp dir), `SECRET_KEY`, fake `CLOUDINARY_*`, `ENVIRONMENT=test`, `CORS_ORIGINS=http://allowed.example`, `ALLOWED_EMAIL_DOMAINS=gmail.com`. Settings are read at import time, so order matters.
2. **Engine swap.** A SQLite engine with `StaticPool` replaces `app.database.engine` / `SessionLocal`, so no PostgreSQL is needed.
3. **No lifespan.** `app.router.lifespan_context` is replaced by a no-op, skipping Alembic migrations and the cleanup loop.
4. **Autouse fixture `fresh_database`.** Drops and recreates all tables and clears every rate-limiter's state before each test (so limits from one test cannot leak into another).
5. **Fixtures/factories:** `client` (`TestClient`), `db_session`, `make_user(db, email?, password?, is_admin?, is_active?)`, `auth_headers(user)`, `make_listing(db, owner, title?)`, `make_interest(db, listing, user, status)`, `register_payload(email)`.

Because the tests use SQLite, behaviour that depends on PostgreSQL specifics (native enums, advisory locks, `ILIKE` semantics) is **not** exercised. The migration path is likewise untested by pytest; CI validates it only indirectly through the container build, and production applies it on startup.

## Test inventory

### `test_auth.py` – authentication and abuse controls

Unauthenticated access denied · invalid token rejected · `alg: none` forged token rejected · deactivated user rejected · identical login-failure messages · login success returns bearer token · password hash uses Argon2id · password policy rejects letters-only and short passwords · strong password registers · disallowed email domain rejected · login rate limit returns `429` with `Retry-After` · registration rate limit returns `429`.

### `test_authorization.py` – access control

Profile endpoint isolation · horizontal escalation blocked for listing update and delete · owner can update own listing · admin stats blocked for non-admins (vertical escalation) · admin endpoints require authentication · admin can read stats · cannot show interest in own listing · contact details blocked before acceptance · blocked for a third party · visible to both participants after acceptance.

### `test_input_validation.py` – input handling and leakage

Missing fields rejected · oversized values rejected · SQL-metacharacter and quote searches return cleanly · registration/profile responses contain no `password_hash` · error responses don't leak internals · rate limiter bounds memory under key rotation · rate-limit window expiry.

### `test_security_headers.py` – headers and CORS

Baseline headers present · HSTS absent when disabled / present when enabled · CSP exempts docs paths · request ID returned, and a malformed client ID is not echoed · CORS allows the configured origin and blocks unknown preflight origins · wildcard origin guard · sensitive endpoints send `no-store`.

## Writing new tests

- Import helpers with `from tests.conftest import auth_headers, make_user, make_listing, ...`.
- Create users/listings directly in the DB via `db_session` instead of going through the API, then call the API with `client` and `auth_headers(user)`.
- For any new route, cover at minimum: anonymous → `401/403`; wrong user → `403`; correct user → success; invalid input → `422`.
- To test settings-dependent behaviour (HSTS, limits) use `monkeypatch.setattr(settings, "...", value)`; see `test_security_headers.py`.
- Cloudinary calls are not mocked by the existing tests (none upload images). Mock `app.services.cloudinary.upload_image` / `delete_image` if you add tests for listing creation or deletion with images.
- Prefer fixing gaps listed in [Known Limitations](Known-Limitations-and-Gaps.md) with a failing test first.

## Manual and deployment test plan

[docs/security/TEST_PLAN.md](../docs/security/TEST_PLAN.md) lists deployment checks: API availability, docs disabled in production, CORS from allowed vs unapproved origin, authorization, image upload, secret exposure, database TLS, concurrent migrations, restore drill, logging, and browser CSP behaviour. [ACCEPTANCE_CRITERIA.md](../docs/security/ACCEPTANCE_CRITERIA.md) maps each requirement to its evidence.

### ZAP scan

```powershell
# API scan (needs the API running with docs enabled, i.e. ENVIRONMENT != production)
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1

# Passive scan of the SPA
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1 -Mode baseline -Target http://host.docker.internal:5173
```

Reports go to `zap-reports/` (`zap-report.html`, `.md`, `.json`). Use synthetic data; never run against production.

### API contract diff

```powershell
python scripts/security/openapi_diff.py
```

Output sections: **OFFERED but never consumed** (backend routes the SPA doesn't call – e.g. listing `PUT`, need `DELETE`, depending on current state of `api.js`) and **CONSUMED but not offered** (broken frontend calls). It first tries `http://127.0.0.1:8000/openapi.json`, then imports the app offline (requires backend settings to be resolvable from `backend/.env`).
