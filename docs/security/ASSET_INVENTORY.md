# Asset Inventory

## Services

| Asset | Location | Exposure and controls |
| --- | --- | --- |
| Frontend | `src/`, Cloudflare Pages | Public HTTPS SPA; generated `_headers` configures browser-facing headers |
| API | `backend/`, Google Cloud Run | Public HTTPS; authentication and authorization enforced by FastAPI |
| Database | Neon PostgreSQL | External managed database; TLS connection from Cloud Run; credentials in Secret Manager |
| Images | Cloudinary | Uploaded through the API using server-side credentials |
| CI/CD | `.github/workflows/` | GitHub Actions; Google authentication uses Workload Identity Federation |
| Local database | `backend/docker-compose.yml` | Development only; port 5432 bound to localhost |

## Secrets

| Secret | Storage | Notes |
| --- | --- | --- |
| `NEON_DATABASE_URL` | Google Secret Manager | TLS-enabled PostgreSQL URL; never put in frontend settings |
| `SECRET_KEY` | Google Secret Manager | JWT signing key; rotating it invalidates issued tokens |
| `CLOUDINARY_CLOUD_NAME` | Google Secret Manager | Used by the API only |
| `CLOUDINARY_API_KEY` | Google Secret Manager | Used by the API only |
| `CLOUDINARY_API_SECRET` | Google Secret Manager | Used by the API only |
| `CLOUDFLARE_API_TOKEN` | GitHub Actions secret | Scoped to deploy the Pages project |
| Google WIF configuration | GitHub repository variables and Google IAM | No long-lived service-account key |

`VITE_API_BASE_URL` is public configuration, not a secret. It is embedded in the frontend build and must point to the Cloud Run API URL ending in `/api`.

## Data and recovery

Application records are stored in Neon. Enable backup and point-in-time recovery according to the selected Neon plan. Listing images are stored in Cloudinary. Verify database and media recovery procedures before launch.

## Runtime notes

The Cloud Run container listens on the platform-provided `PORT`. Runtime secrets are read from Secret Manager. Alembic migrations run on startup and use a PostgreSQL advisory lock to serialize concurrent starts. Rate-limit counters are process-local and are not shared across Cloud Run instances.
