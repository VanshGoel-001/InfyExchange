# Security Acceptance Criteria

**Status key:** Repository checks are automated where possible. Cloud configuration and recovery require evidence from the deployed services.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Protected API routes require authentication | Automated | Backend authorization tests |
| Users cannot modify another user's resources | Automated | Ownership and contact-access tests |
| Untrusted input is validated and database queries are parameterized | Automated | Validation tests and static analysis |
| Production secrets are absent from frontend assets | Automated/manual | Build inspection; only `VITE_API_BASE_URL` is public |
| API uses HTTPS and production docs are disabled | Deployment verification | Cloud Run service URL, `/health`, and `/docs` behavior |
| Cloud Run has bounded scaling and connection pools | Deployment verification | Service configuration and Neon connection limit |
| GitHub deploys with Workload Identity Federation | Deployment verification | No service-account key; restricted repository/ref binding |
| Runtime secrets are read from Secret Manager | Deployment verification | Runtime service account has access only to required secrets |
| Neon access uses TLS and a least-privilege app role | Deployment verification | Neon configuration and successful application connection |
| Database backup and restore are tested | Deployment verification | Neon retention/PITR setting and recorded restore test |
| Cloudflare Pages uses the correct API URL and CSP headers | Deployment verification | Page response headers and browser checks |
| Cloud logs are retained and security events alert operators | Deployment verification | Cloud Logging retention and alert test |

Do not mark deployment requirements complete without recording the relevant configuration or test output. See [the runbook](SECURITY_RUNBOOK.md) for deployment steps.
