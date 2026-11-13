# Backend Guide

The API lives in `backend/app/`. It is a synchronous FastAPI application (sync SQLAlchemy sessions, sync route handlers except the listing-creation endpoint, which is `async` because it awaits file reads).

## Module map

| Path | Role |
| --- | --- |
| `main.py` | Creates the `FastAPI` app, wires middleware, routers, exception handlers, `/` and `/health`, the lifespan (migrations + cleanup task) and a patched OpenAPI schema |
| `config.py` | `Settings` (pydantic-settings) and the module-level singleton `settings` |
| `database.py` | `engine`, `SessionLocal`, declarative `Base`, `get_db()` dependency |
| `dependencies.py` | `get_current_user`, `get_current_admin` |
| `middleware.py` | `RequestContextMiddleware`, `SecurityHeadersMiddleware` |
| `routers/` | `auth`, `users`, `listings`, `interests`, `needs`, `admin` |
| `schemas/` | Pydantic models: `auth`, `user`, `listing`, `interest`, `need` |
| `models/` | ORM models: `User`, `Listing`, `ListingImage`, `Interest`, `Need`, `AuditLog` |
| `services/auth.py` | Argon2id hashing, JWT create/decode |
| `services/cloudinary.py` | Image validation, upload, delete |
| `services/rate_limit.py` | In-memory sliding-window limiter and shared limiter instances |
| `services/cleanup.py` | Expired-data deletion and the 24 h loop |
| `services/migration.py` | Programmatic `alembic upgrade head` with an advisory lock |
| `utils/enums.py` | All enums shared by models and schemas |
| `utils/logging_utils.py` | Logging setup with request IDs and UTC timestamps |
| `run_cleanup.py` | CLI entry for one-shot cleanup |

## Startup and migrations

`main.py` → `lifespan`:

1. `setup_logging()` has already run at import time (stdout handler, UTC ISO-8601 timestamps, `[request_id]` in every line).
2. `apply_migrations()`:
   - picks `DATABASE_URL_UNPOOLED` if set, else `DATABASE_URL`;
   - opens a short-lived, `NullPool` engine, takes `pg_advisory_xact_lock(74193820416)` on PostgreSQL, and runs `alembic upgrade head` on that same connection;
   - **on failure**: logs `Database migrations failed`; re-raises (aborting startup) only when `ENVIRONMENT=production`, otherwise continues.
3. Logs `service_started environment=…` and spawns `cleanup_loop()` as a task.
4. On shutdown the task is cancelled and `service_stopped` is logged.

Because `Config("alembic.ini")` is a relative path, the process must start in `backend/` (the Dockerfile copies `alembic.ini` and `alembic/` next to `app/` in `/app` for the same reason).

Production vs development differences set in `main.py`: `/docs`, `/redoc`, `/openapi.json` are `None` when `ENVIRONMENT.lower() == "production"`.

A custom `app.openapi` rewrites OpenAPI 3.1 `contentMediaType: application/octet-stream` file fields into `type: string, format: binary` so Swagger UI renders upload inputs for `POST /api/listings`.

## Configuration

All settings are defined in `config.py` and read from environment variables (case-insensitive) or `backend/.env`. Unknown variables are ignored (`extra="ignore"`). Derived helpers: `cors_origin_list`, `allowed_email_domain_list` (comma-split, trimmed, lower-cased for domains). Full table: [Configuration Reference](Configuration-Reference.md).

## Database access

```python
engine = create_engine(settings.database_url,
                       pool_pre_ping=True,
                       pool_size=settings.db_pool_size,
                       max_overflow=settings.db_max_overflow,
                       pool_recycle=settings.db_pool_recycle)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
```

- `get_db()` yields one session per request and closes it in `finally`.
- `autoflush=False`: pending changes are flushed on `commit()` or explicit `flush()` (the audit logger relies on `flush()`).
- The runtime engine uses the **pooled** URL (`DATABASE_URL`, Neon's pgbouncer endpoint). Migrations use the **direct** URL. In Cloud Run each instance gets `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`, so at most 5 connections per instance and 15 with the maximum of 3 instances.
- Listing queries use `joinedload(owner)` plus `selectinload(images)` to avoid N+1 queries; detail queries use `joinedload` for both.

## Authentication internals

- `services/auth.py` pins `PasswordHash((Argon2Hasher(),))` so a library upgrade cannot silently switch algorithms.
- `create_access_token(user_id)` → HS256 JWT with claims `sub` (stringified user id) and `exp` (now + `ACCESS_TOKEN_EXPIRE_MINUTES`, default 10080 = 7 days). `decode_access_token` pins `algorithms=[settings.algorithm]`, rejecting `alg: none` forgeries.
- `get_current_user` (HTTP Bearer): decode → load user by id → reject if missing (`401 User not found`) or inactive (`403`). Each failure writes a `security` log line containing the client IP but never the token.
- `get_current_admin` layers an `is_admin` check on top (`403` + `admin_access_denied` log).
- The token carries no role or admin claim: admin rights are re-read from the database on every request, so revoking admin takes effect immediately. There is no token revocation list, refresh token, logout endpoint, or password-change flow.

## Image handling (`services/cloudinary.py`)

`upload_image(file, listing_id)`:

1. Reject unless `file.content_type` ∈ {`image/jpeg`, `image/png`, `image/webp`}.
2. Read in 64 KiB chunks, aborting once the total exceeds `MAX_IMAGE_SIZE_MB` (OOM guard).
3. `_validate_image_magic_bytes`: ≥12 bytes and JPEG (`FF D8 FF`), PNG (8-byte signature), or WebP (`RIFF…WEBP`).
4. Upload via `cloudinary.uploader.upload` in `asyncio.to_thread` to `infyexchange/listings/<listing_id>`; returns `{public_id, url}` (`secure_url`).

`delete_image(public_id)` calls `uploader.destroy(..., invalidate=True)`. Cloudinary is configured at import time from settings with `secure=True`. No malware scanning is performed.

## Rate limiting (`services/rate_limit.py`)

`InMemoryRateLimiter(max_requests, window_seconds, name)` stores a list of timestamps per key and drops those older than the window on each check. A periodic prune removes empty keys and caps tracked keys at `MAX_TRACKED_KEYS = 10_000` (evicting the oldest) so key-rotation attacks cannot exhaust memory.

Helpers:

- `client_key(request, scope)` → `"<scope>:<ip>"`.
- `account_key(email)` → `"acct:" + sha256(lower(email))[:32]` so raw emails never sit in limiter state.
- `rate_limit_dependency(limiter, scope, detail)` → a FastAPI dependency (used by the admin router).
- `limiter.enforce(key, detail)` → raises `429` with `Retry-After`.

Limiter instances (`login_limiter`, `account_login_limiter`, `register_limiter`, `create_limiter`, `read_limiter`, `contact_limiter`, `admin_limiter`) are created at import from `settings`. State is per process: it resets on restart and is not shared between Cloud Run instances or Uvicorn workers.

## Expiry cleanup (`services/cleanup.py`)

`cleanup_expired_data()` opens its own session and:

1. selects listings with `expires_at <= utcnow()` (any status), deletes their Cloudinary images one by one (logging, not raising, on failure) and deletes the rows;
2. does the same for needs (no external assets);
3. commits once and logs the counts.

`cleanup_loop()` runs it, logs and survives any exception, then sleeps 24 h. `run_cleanup.py` configures basic logging and calls it once.

## Logging

- Format: `<UTC timestamp>Z LEVEL logger [request_id] message`.
- `security` logger events: `auth_failed reason=invalid_token|user_not_found`, `deactivated_account_access`, `admin_access_denied`, `login_failed`, `service_started`/`service_stopped` (via `get_security_logger`), plus `rate_limit_exceeded limiter=… window=… max=…` from the limiter module.
- Rule from `logging_utils.py`: never log passwords, tokens or raw personal data.

## Adding a feature – checklist

1. **Model** → add/modify the class in `models/`, register it in `models/__init__.py`.
2. **Migration** → `alembic revision --autogenerate`, review, commit (see [Data Model](Data-Model.md#migrations)).
3. **Schemas** → request/response Pydantic classes; use `ConfigDict(from_attributes=True)` for ORM responses.
4. **Router** → add the endpoint; use `Depends(get_current_user)` (or admin) for anything non-public; pick or add a rate-limit bucket for anything that writes or reveals data; enforce ownership explicitly (`owner_id != current_user.id → 403`).
5. **Admin actions** → call `log_admin_action(...)` *before* `db.commit()` so the audit row commits atomically with the change.
6. **Frontend** → add a function to `src/services/api.js` and run `python scripts/security/openapi_diff.py` to confirm the new route is both offered and consumed.
7. **Tests** → add cases to `backend/tests/` for authorization (owner vs stranger vs anonymous) and validation.
8. **Docs** → update [API Reference](API-Reference.md) and, for security-relevant changes, `docs/security/`.

## Style notes observed in the codebase

- Handlers return plain dicts built by `_serialize_*` helpers where the ORM object needs derived fields (owner name, first image URL); other handlers return ORM objects directly and rely on `response_model`.
- Errors are raised as `HTTPException` with human-readable `detail` strings; the SPA surfaces these verbatim.
- Strings from clients are `.strip()`-ed before being stored (titles, locations, descriptions, names, phones).
- Search uses `ILIKE '%term%'` with the term bound as a parameter (injection-safe, but `%`/`_` in user input act as wildcards and the pattern cannot use a normal index).
