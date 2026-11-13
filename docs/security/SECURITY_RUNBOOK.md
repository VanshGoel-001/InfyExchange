# Operations Runbook

This runbook covers the production deployment on Cloudflare Pages, Google Cloud Run, and Neon. Do not put secret values in Git, issues, or logs.

## Production setup

### Google Cloud

Enable Cloud Run, Artifact Registry, Secret Manager, IAM Credentials, and Security Token Service APIs. Create a Docker Artifact Registry repository before deployment. Configure Workload Identity Federation for this repository and only the `deploy/neon-cloudrun-cloudflare-pages` branch; do not create a long-lived service-account key for GitHub Actions.

Set the repository or `neon-staging` environment variables for the CI deployment workflow as listed in the [Configuration Reference](../../wiki/Configuration-Reference.md#github-actions-variables-and-secrets).

Restrict the WIF provider condition to the exact GitHub repository and deployment branch. Grant the deployer only Artifact Registry Writer, Cloud Run deployment, and runtime service-account impersonation permissions. Grant the runtime account Secret Manager access only to the six required secrets. Set the GitHub `neon-staging` environment to require reviewer approval and allow deployments only from the dedicated branch.

Create the Artifact Registry repository once:

```bash
gcloud artifacts repositories create "$ARTIFACT_REGISTRY_REPOSITORY" \
	--repository-format=docker \
	--location="$GCP_REGION" \
	--project="$GCP_PROJECT_ID"
```

Create the six Secret Manager secrets mapped in the [Configuration Reference](../../wiki/Configuration-Reference.md#google-secret-manager-secrets). The Neon URLs must use the `postgresql+psycopg://` scheme with TLS (`sslmode=require`); `SECRET_KEY` must be at least 32 random bytes.

Use a Neon connection string suitable for the application’s connection pattern. The runtime pool is configured for at most 5 connections per instance, with up to 3 Cloud Run instances by default.

### Neon

Use a dedicated application role with only the permissions the app needs. Keep the connection string in Secret Manager, not in GitHub variables or the Pages build. Enable the backup/PITR retention appropriate to the data and subscription plan. Test restoring a branch or backup before launch and periodically afterward.

### Cloudflare Pages

Set the Cloudflare variables and secret listed in the [Configuration Reference](../../wiki/Configuration-Reference.md#github-actions-variables-and-secrets) for the `Deploy Cloudflare Pages` workflow.

The CI workflow runs checks first, then deploys Cloud Run, waits for its health check, and deploys the matching Cloudflare Pages branch. On the first deployment, set `VITE_API_BASE_URL` to the Cloud Run service URL ending in `/api` before pushing the deployment branch.

## Deploy and verify

A push to `deploy/neon-cloudrun-cloudflare-pages` runs CI, then the Cloud Run and Pages deployments. CI builds the container once for release, attaches BuildKit provenance and SBOM metadata, scans it for high/critical vulnerabilities, retains a CycloneDX SBOM, and deploys the same image by digest. Startup applies pending Alembic migrations using the direct URL. PostgreSQL advisory locking serializes migrations when Cloud Run starts multiple instances or revisions concurrently. The `main` branch remains on its separate Oracle/Cloudflare deployment strategy.

Check the service and health endpoint:

```bash
gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)'
curl -fsS "$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)')/health"
```

Then verify from the Pages origin: login, listing creation, image upload, and the expected CORS policy. Use synthetic accounts and non-production data for security scans.

## Logs and alerts

Cloud Run writes application logs to Cloud Logging. Review request IDs and `security` events for failed logins, denied admin access, and rate-limit responses. Configure alerting and retention in Google Cloud; do not log tokens, passwords, database URLs, or Cloudinary secrets.

## Rollback

Cloud Run keeps prior revisions. Route traffic back to the last known-good revision with `gcloud run services update-traffic`. Revert the source change and push to the Neon deployment branch to redeploy. Before rolling back a database migration, confirm that the previous application revision is compatible with the current schema; destructive schema changes require a separate recovery plan.

For database recovery, use Neon’s documented point-in-time recovery or restore workflow. Record restore tests and measured recovery time.

## Security scans

The API disables `/docs`, `/redoc`, and `/openapi.json` in production. Run the ZAP API scan against a staging deployment with documentation enabled, not production:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1
```

Triage high-severity findings before release. Never run load or destructive tests against production.
