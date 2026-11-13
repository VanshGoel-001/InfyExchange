# Test Plan

Use isolated local or staging data. Do not run destructive or load tests against production. Redact secrets from all captured output.

## Automated checks

The frontend and backend commands (`npm audit`, `npm run build`, `pytest`, Bandit, `pip-audit`) are listed in the [README](../../README.md#verify); the test inventory is in the [wiki](../../wiki/Testing.md). CI also validates local Compose configuration and builds the API container. The Cloud Run deployment workflow runs only after CI passes on a push to `deploy/neon-cloudrun-cloudflare-pages`; the Pages workflow follows a successful API deployment.

## Deployment checks

| Check | Procedure | Expected |
| --- | --- | --- |
| API availability | Request the Cloud Run service URL at `/health` | HTTPS succeeds and returns healthy status |
| Production surface | Request `/docs`, `/redoc`, `/openapi.json` | Documentation endpoints are disabled |
| CORS | Send preflight requests from the Pages origin and an unapproved origin | Only the configured Pages origin is allowed |
| Authorization | Call protected routes without a token and attempt cross-user mutations | Unauthenticated calls are rejected; cross-user actions are denied |
| Image upload | Upload an allowed image through the API using a synthetic account | Image is stored in Cloudinary; no local file dependency |
| Secrets | Inspect Cloud Run configuration and frontend build output | Runtime secrets come from Secret Manager and are absent from frontend assets |
| Database TLS | Verify the Neon URL uses TLS and the application connects successfully | Database traffic is encrypted; credentials are not exposed in logs |
| Migrations | Start/revise the service while a migration is pending | Migration completes once; concurrent instance starts serialize on the PostgreSQL advisory lock |
| Recovery | Restore a Neon backup/PITR point to a test branch and verify records | Restored data is usable and recovery time is recorded |
| Logging | Trigger a test authentication failure and inspect Cloud Logging | Request ID and security event appear without passwords, tokens, or secrets |
| Browser policy | Load Pages and exercise login, navigation, and uploads with developer tools open | Correct CSP and other headers; no unexpected policy violations |

## Dynamic scanning

Run the ZAP API scan against a staging API with documentation enabled. Production intentionally disables the OpenAPI endpoints. Use synthetic data and review every high-severity finding before release.
