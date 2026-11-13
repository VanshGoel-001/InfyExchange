# Operations & Troubleshooting

Day-two guide for running InfyExchange in production (Cloud Run + Neon + Cloudflare Pages + Cloudinary). The formal runbook is [docs/security/SECURITY_RUNBOOK.md](../docs/security/SECURITY_RUNBOOK.md); this page adds code-level context and recipes. Variables like `$CLOUD_RUN_SERVICE` are the same values configured in GitHub ([Configuration Reference](Configuration-Reference.md#github-actions-variables-and-secrets)).

## Live deployment snapshot

Verified from outside on **2026-11-12** (public requests only; no credentials used):

| Item | Value / result |
| --- | --- |
| Web | <https://infyexchange.pages.dev/> → 200; SPA assets under `/assets/`; headers include `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, and `Content-Security-Policy-Report-Only` (so the CSP is **not** enforced yet) |
| API | Cloud Run service `infyexchange-api`, region `asia-southeast1` (URL of the form `https://infyexchange-api-<project-number>.asia-southeast1.run.app`) |
| `/health` | `{"status":"healthy"}` |
| `/docs` | 404 – docs disabled, so `ENVIRONMENT=production` is in effect |
| CORS | `access-control-allow-origin: https://infyexchange.pages.dev` for that origin |
| API headers | `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, strict API CSP, `X-Request-ID` present |
| **HSTS** | **Absent** on the API response, although `cloud-run-deploy.yml` sets `HSTS_ENABLED=true`. Inspect the running revision's env vars (`gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='yaml(spec.template.spec.containers[0].env)'`) and redeploy if needed |
| Data | `GET /api/listings` returned `[]` – no listings posted yet |

## Health and status

| Check | Command | Healthy |
| --- | --- | --- |
| Service URL | `gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)'` | prints `https://…run.app` |
| API health | `curl -fsS "<service-url>/health"` | `{"status":"healthy"}` |
| Docs disabled | `curl -i "<service-url>/docs"` | `404` |
| CORS | `curl -i -X OPTIONS "<service-url>/api/listings" -H "Origin: https://evil.example" -H "Access-Control-Request-Method: GET"` | no `access-control-allow-origin` |
| SPA headers | `curl -sI https://<pages-origin>/` | nosniff, frame denial, CSP(-Report-Only) |

`/health` only proves the process is up; it does **not** query the database.

## Logs

Cloud Run writes stdout to Cloud Logging. Every line has the form `2026-… INFO logger [request_id] message`. Useful patterns:

| Search for | Meaning |
| --- | --- |
| `service_started` / `service_stopped` | Instance lifecycle |
| `Database migrations failed` | Startup migration error (fatal in production) |
| `login_failed` | Failed login with client IP |
| `auth_failed reason=` | Invalid token or deleted user |
| `deactivated_account_access` | Deactivated user used a token |
| `admin_access_denied` | Non-admin called an admin route |
| `rate_limit_exceeded limiter=` | A limiter tripped |
| `Cleanup deleted N listing(s) and M need(s)` | Expiry job result |
| `Failed to delete expired image` | Cloudinary delete failed during cleanup |
| `Database error during request` / `Unhandled exception` | 500s, with stack traces |

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="'"$CLOUD_RUN_SERVICE"'" AND textPayload:"login_failed"' \
  --project "$GCP_PROJECT_ID" --limit 50 --freshness 1d
```

To trace one user's problem, ask for the `X-Request-ID` response header (the SPA doesn't display it; browser dev tools do) and search the logs for it.

Alerting, retention and dashboards are not defined in the repository – configure log-based metrics for repeated `login_failed`, `admin_access_denied`, `Database migrations failed` and 5xx rates.

## Routine tasks

### Promote or demote an admin

Use the admin console (Users tab) once you have one admin. For the first admin or emergency recovery, run SQL against the **direct** Neon connection (Neon SQL editor or `psql`):

```sql
UPDATE users SET is_admin = true WHERE email = 'person@gmail.com';
```

### Deactivate a user immediately

Admin console → Users → deactivate (writes an `UPDATE_USER` audit entry). Their token stops working on the next request. Remember their listings remain visible until removed or status-changed.

### Rotate the JWT signing key

1. Add a new version of the `SECRET_KEY` secret in Secret Manager.
2. Redeploy or restart the service so a new revision reads `:latest`.
3. **All users are logged out** (existing tokens fail signature verification and the SPA clears them on the resulting `401`).

### Rotate Cloudinary or database credentials

Update the Secret Manager version and redeploy. For Neon, rotate the role password, update both the pooled and direct secrets together, then redeploy.

### Expiry cleanup

The API schedules its own cleanup inside each instance: one run at startup, then every 24 h. Because instances are ephemeral and Cloud Run may not give background tasks CPU between requests (inference – depends on the service's CPU-allocation setting, which the deploy command does not change from the default), do not rely on it for strict timing. Recommended: create a Cloud Run Job or Cloud Scheduler trigger that runs `python -m app.run_cleanup` using the same image and secrets, e.g. daily. Running it more than once is safe (it only deletes rows past `expires_at`).

### Moderation clean-up of images

Admin deletions do not remove Cloudinary assets ([Known Limitations](Known-Limitations-and-Gaps.md)). Periodically compare the `infyexchange/listings/<id>` folders in Cloudinary with existing listing IDs and remove orphans.

## Capacity and connection budget

- Cloud Run: 1 vCPU, 1 GiB, concurrency 40, max 3 instances (`--max 3`). Uvicorn also caps at 200 concurrent connections.
- Database: each instance may use up to `DB_POOL_SIZE + DB_MAX_OVERFLOW` = 3 + 2 = **5** connections → at most **15** across three instances, plus 1 short-lived connection per migration run. Check this against the Neon plan before raising `--max` or the pool sizes.
- Sync route handlers run in Starlette's thread pool, so concurrency per instance is bounded by the thread pool and DB pool, not just the Cloud Run setting.
- Rate-limit memory: ≤ 10 000 tracked keys per limiter instance.

## Backup and recovery

- **Database:** rely on Neon backups/PITR per plan. Procedure: restore to a new Neon branch at a chosen timestamp, verify counts of `users`, `listings`, `interests`, then repoint the secrets if promoting that branch. Record the recovery time of each drill.
- **Images:** Cloudinary is the only copy of uploaded photos; DB rows only keep public IDs and URLs. Enable Cloudinary backup if the photos matter.
- **Config:** everything else is reproducible from Git plus the secret values held in Secret Manager.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Deploy fails at "Validate deployment settings" | A GitHub variable is empty | Add it (names in the error) |
| Deploy fails at Trivy | Fixable HIGH/CRITICAL vuln in the base image or a dependency | Bump the dependency/base image (Dependabot may already have a PR); rebuild |
| Pages build fails with `VITE_API_BASE_URL must end with "/api"` | Variable missing `/api` or has a trailing slash | Set `https://<api-host>/api` |
| SPA loads but every API call fails with CORS | `CORS_ORIGINS` isn't the exact Pages origin (scheme + host, no trailing slash/path) | Fix the variable and redeploy the API |
| SPA deep links 404 | `_redirects` missing from the build | Ensure `public/_redirects` is present and `dist/` contains it |
| New Cloud Run revision never becomes ready | Startup migration failed (production aborts) or a secret is missing/inaccessible | Read revision logs for `Database migrations failed`; verify runtime service account has secret access and the direct URL works |
| `psycopg` connection / SSL errors | URL scheme not `postgresql+psycopg://` or `sslmode=require` missing | Fix the secret value |
| Random 500 "A database error occurred" | Connection exhaustion, Neon scale-to-zero wake-up, or a constraint/length error | Check logs (full error is logged); `pool_pre_ping=True` already recovers stale connections |
| `429` for normal users | Limits are per IP; many users behind one NAT, or tests/scans | Raise `RATE_LIMIT_*` carefully or move to a shared store |
| `401 Invalid or expired token` right after login | `SECRET_KEY` changed between instances/revisions | Ensure a single `SECRET_KEY` secret; users re-login |
| `403 Account is deactivated` | Admin deactivated the user | Reactivate in the admin console |
| Images fail to upload (`400 Failed to upload images`) | Wrong Cloudinary credentials, network error, or invalid file | Check logs for `Image upload failed for listing …`; the listing is rolled back automatically |
| Listing disappeared | Reached `expires_at` (30 days) and was cleaned up, or an admin removed it | Check `audit_logs` for `DELETE_LISTING` |
| Contact reveal says not available | Interest isn't `ACCEPTED` or caller isn't a participant | Owner must accept first |
| Local: `ValidationError` on startup | Missing env var or wrong working directory | Run from `backend/` with `.env` filled in |
| Local: tests can't find `app` | Running pytest from the wrong directory | Run from `backend/` |

## Incident basics

1. **Contain:** if credentials may be exposed, rotate them (above) and redeploy; to cut access immediately, deactivate affected users or temporarily route traffic away with `gcloud run services update-traffic`.
2. **Investigate:** use request IDs and `security` log lines; check `audit_logs` for admin actions.
3. **Recover:** roll back the Cloud Run revision if a release caused it; restore data from Neon if needed.
4. **Review:** capture the timeline and add a regression test or alert.
