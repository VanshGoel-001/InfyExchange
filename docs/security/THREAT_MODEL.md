# Threat Model

This model covers the application deployed on Cloudflare Pages, Google Cloud Run, Neon, and Cloudinary. Cloud-provider configuration must be verified in the deployed projects; repository settings alone do not prove it is correct.

## Assets

- Account credentials, JWT signing key, and session tokens
- User contact details and marketplace records
- Neon database and Cloudinary images
- Cloud Run and GitHub deployment identities
- Availability and integrity of the API

## Threats and controls

| Threat | Controls | Remaining work |
| --- | --- | --- |
| Unauthorized access | HS256 JWT validation; authentication on protected routes; ownership and admin checks | Keep tests and authorization review current |
| Credential theft | Argon2id password hashing; uniform login errors; login limits; secrets in Secret Manager | MFA is not implemented; JWT is stored in browser `localStorage` |
| API abuse | Request limits, concurrency limits, bounded Cloud Run instances and database pools | Rate-limit state is per instance; evaluate provider protections and shared storage as traffic grows |
| Malicious uploads | Type and content validation; size limits; Cloudinary storage | No malware scanning |
| Database exposure | Neon TLS connection; credentials in Secret Manager; application role | Verify database access controls and least privilege |
| Data loss | Neon backup and recovery features | Select suitable retention/PITR and test restores |
| Supply-chain compromise | Locked dependencies, CI audits, container build | Pin container image digests and review workflow action versions |
| Cloud misconfiguration | GitHub Workload Identity Federation; separate deploy/runtime service accounts | Verify IAM bindings, Cloud Run ingress, Pages settings, and secret access |
| XSS and token theft | React escaping; CSP generated for Pages; API security headers | CSP is report-only until browser validation; no token revocation flow |
| Weak detection | Request IDs, security events, Cloud Logging integration | Configure retention, dashboards, and alerts |

## Operational notes

Cloud Run is a public HTTPS API by design. CORS only controls browser behavior; it is not API authentication. Use JWT authorization for protected operations and configure Cloud Run ingress and identity settings deliberately.

Alembic migrations run on application startup. PostgreSQL transaction-scoped advisory locks serialize concurrent startup migrations. Schema changes must remain compatible with the previous Cloud Run revision during rollout.

The API trusts forwarded headers from its hosting proxy. Review Cloud Run ingress and proxy behavior if the service's network path changes.

## Residual risks

- A token exposed from `localStorage` can be replayed until it expires.
- In-memory rate limits vary by Cloud Run instance and reset on restart.
- Cloud-provider IAM, database recovery, and alerting remain deployment responsibilities.
- Uploaded images are not malware-scanned.
