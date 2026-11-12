# Operations Runbook

This runbook covers the production deployment on Cloudflare Pages, Google Cloud Run, and Neon. Do not put secret values in Git, issues, or logs.

## Production setup

### Google Cloud

Enable Cloud Run, Cloud Build, Artifact Registry, Secret Manager, and IAM APIs. Configure Workload Identity Federation for this repository and the `main` branch; do not create a long-lived service-account key for GitHub Actions.

Set these repository variables for the `Deploy Cloud Run` workflow:

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project ID |
| `GCP_REGION` | Cloud Run region |
| `CLOUD_RUN_SERVICE` | API service name |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full workload identity provider resource name |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | CI deployer service-account email |
| `CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT` | Runtime service-account email |
| `CORS_ORIGINS` | Exact Cloudflare Pages origin |

Grant the deployer permission to deploy Cloud Run services, build and publish the source image, and impersonate the runtime service account. Grant the runtime account `Secret Manager Secret Accessor` on the required secrets.

Create these Secret Manager secrets:

| Secret | Value |
| --- | --- |
| `NEON_DATABASE_URL` | Neon connection URL using `postgresql+psycopg://` and TLS (`sslmode=require`) |
| `SECRET_KEY` | Random JWT signing key, at least 32 random bytes |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |

Use a Neon connection string suitable for the application’s connection pattern. The runtime pool is configured for at most 5 connections per instance, with up to 3 Cloud Run instances by default.

### Neon

Use a dedicated application role with only the permissions the app needs. Keep the connection string in Secret Manager, not in GitHub variables or the Pages build. Enable the backup/PITR retention appropriate to the data and subscription plan. Test restoring a branch or backup before launch and periodically afterward.

### Cloudflare Pages

Set these repository values for the `Deploy Cloudflare Pages` workflow:

| Name | Type | Value |
| --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Variable | Cloudflare account ID |
| `CLOUDFLARE_PAGES_PROJECT` | Variable | Pages project name |
| `VITE_API_BASE_URL` | Variable | Cloud Run service URL ending in `/api` |
| `CLOUDFLARE_API_TOKEN` | Secret | Token scoped to deploy the Pages project |

The API workflow completes before the Pages workflow starts. On the first deployment, deploy the API, copy its HTTPS service URL from Cloud Run, set `VITE_API_BASE_URL`, and rerun the Pages deployment if its first attempt ran before the variable was set.

## Deploy and verify

A push to `main` runs CI, deploys the API, then deploys the frontend. The API workflow applies pending Alembic migrations during startup. PostgreSQL advisory locking serializes migrations when Cloud Run starts multiple instances or revisions concurrently.

Check the service and health endpoint:

```bash
gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)'
curl -fsS "$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)')/health"
```

Then verify from the Pages origin: login, listing creation, image upload, and the expected CORS policy. Use synthetic accounts and non-production data for security scans.

## Logs and alerts

Cloud Run writes application logs to Cloud Logging. Review request IDs and `security` events for failed logins, denied admin access, and rate-limit responses. Configure alerting and retention in Google Cloud; do not log tokens, passwords, database URLs, or Cloudinary secrets.

## Rollback

Cloud Run keeps prior revisions. Route traffic back to the last known-good revision with `gcloud run services update-traffic`. Revert the source change and push to `main` to redeploy. Before rolling back a database migration, confirm that the previous application revision is compatible with the current schema; destructive schema changes require a separate recovery plan.

For database recovery, use Neon’s documented point-in-time recovery or restore workflow. Record restore tests and measured recovery time.

## Security scans

The API disables `/docs`, `/redoc`, and `/openapi.json` in production. Run the ZAP API scan against a staging deployment with documentation enabled, not production:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1
```

Triage high-severity findings before release. Never run load or destructive tests against production.
