# Low-Level Design

This document records the application's security controls and the production-specific behavior of Cloud Run, Neon, and Cloudflare Pages.

## Request and data flow

The browser loads the SPA from Cloudflare Pages and calls the FastAPI service on Cloud Run over HTTPS. The API connects to Neon PostgreSQL over TLS and sends image uploads to Cloudinary. Docker Compose runs only a local PostgreSQL database for development.

Cloud Run sets the container `PORT`; the Docker image listens on that value. Runtime credentials are supplied through Google Secret Manager. The frontend receives only the public `VITE_API_BASE_URL` during its build.

## Database and migrations

SQLAlchemy uses a bounded connection pool configured by `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`. Cloud Run currently deploys with a maximum of three instances and per-instance pool limits set in the workflow. Review these limits against the Neon plan before increasing Cloud Run scale.

Pending Alembic migrations run when an API instance starts. PostgreSQL transaction-scoped advisory locking serializes concurrent migration attempts. Migrations should remain backward-compatible with the previous Cloud Run revision during rollout; destructive changes require a staged migration and rollback plan.

Neon provides managed database backups and recovery features according to the selected plan. Enable an appropriate retention/PITR policy and verify a restore before launch.

## Response security

`SecurityHeadersMiddleware` in `backend/app/middleware.py` sets:

| Header | Purpose |
| --- | --- |
| `X-Content-Type-Options: nosniff` | Prevent content-type sniffing |
| `X-Frame-Options: DENY` | Prevent framing |
| `Referrer-Policy` | Restrict referrer information |
| `Permissions-Policy` | Disable unused browser capabilities |
| `Content-Security-Policy` | Restrict API response content |
| `Cache-Control: no-store` | Avoid caching sensitive API responses |
| `Strict-Transport-Security` | Optional HTTPS policy, controlled by `HSTS_ENABLED` |

The SPA has separate response headers generated into `dist/_headers` by `vite.config.js`. Keep CSP in report-only mode until browser testing shows no required behavior is blocked, then enable enforcement and redeploy Pages.

## Authentication and authorization

- JWT uses HS256 with the accepted algorithm pinned during verification.
- Passwords are hashed with Argon2id.
- Protected routes require authentication; admin routes require the admin role.
- Mutations verify resource ownership. Contact details are available to participants only after an interest is accepted.
- Request IDs are returned to clients and included in application logs.

## Rate limiting

The API applies settings-driven sliding-window limits to authentication, registration, writes, reads, contact access, and admin routes. Counters live in process memory, so limits are per Cloud Run instance and reset when an instance restarts. Add a shared store if consistent cross-instance enforcement is needed.

## Remaining risks

- The browser stores JWTs in `localStorage`; an XSS issue could expose a token.
- Rate-limit counters are not shared across instances.
- There is no token revocation or refresh flow.
- Security headers and access controls must be verified against the deployed Cloud Run and Pages services.
- Database recovery depends on the configured Neon plan and a tested restore procedure.
