# High-Level Design

## Architecture

| Component | Technology | Responsibility |
| --- | --- | --- |
| Frontend | React, Vite, Cloudflare Pages | Static application and browser security headers |
| API | FastAPI, Uvicorn, Google Cloud Run | Authentication, marketplace APIs, uploads, and authorization |
| Database | Neon PostgreSQL | Persistent application data |
| Media | Cloudinary | Listing image storage |
| CI/CD | GitHub Actions | Tests, container build, Cloud Run deploy, then Pages deploy |
| Secrets | Google Secret Manager | Runtime database URL, JWT key, and Cloudinary credentials |

```text
Browser ──HTTPS──► Cloudflare Pages
   │
   └──HTTPS──► Cloud Run API ──TLS PostgreSQL──► Neon
                    │
                    └──HTTPS───────────────────► Cloudinary
```

Cloud Run accepts public HTTPS traffic. The container listens on the platform-provided `PORT` (8080 by default). No Nginx or Caddy proxy is part of production. Docker Compose is used only for a local PostgreSQL instance.

## Deployment

A push to `main` runs CI. On success, the Cloud Run workflow builds and deploys the API using GitHub Workload Identity Federation. Runtime credentials are read from Secret Manager. The Pages workflow starts after the Cloud Run workflow succeeds and builds the SPA with `VITE_API_BASE_URL`.

The API applies Alembic migrations during startup. PostgreSQL transaction-scoped advisory locking serializes migration runs across Cloud Run instances. The Cloud Run service is configured with up to three instances and bounded SQLAlchemy pools.

## Security boundaries

- Browser access to the API is limited by the configured `CORS_ORIGINS` list. CORS is not an authentication mechanism; protected routes enforce JWT and ownership checks.
- Cloud Run terminates HTTPS. The API sets response security headers; Cloudflare Pages serves the SPA's generated `_headers` file.
- Database and application credentials are not included in the frontend build. Cloud Run reads them from Secret Manager.
- Listing images are stored in Cloudinary; the API retains the server-side Cloudinary credentials.
- Rate-limit state is in process memory. Limits are per instance and reset when an instance restarts; use a shared store if distributed enforcement is required.

## Operations

Use Cloud Logging for application and security events. Configure Neon backup retention and point-in-time recovery for the selected plan, and verify recovery by restoring a test branch. See [the runbook](SECURITY_RUNBOOK.md), [the threat model](THREAT_MODEL.md), and [the asset inventory](ASSET_INVENTORY.md) for deployment details and residual risks.
