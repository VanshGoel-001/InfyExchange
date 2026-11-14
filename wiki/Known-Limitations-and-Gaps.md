# Known Limitations & Gaps

Findings from reading the code and docs for this wiki. Each item is marked **Verified** (directly observable in the source) or **Inference / verify** (a conclusion that depends on platform behaviour or on settings outside the repository). None of these were changed as part of writing the wiki.

## Product limitations (documented by the README or visible in the UI)

| Limitation | Detail |
| --- | --- |
| No password change, password reset or account deletion | Verified: no such endpoints. Profile editing exists but only for role and joining date (`PATCH /users/me`); name, email and phone are fixed |
| No email verification | Verified |
| Needs have no response workflow | Need cards are display-only (the non-functional "I can help" button was removed). The API has no endpoint for responding to a need, and contact details are only ever revealed for accepted listing enquiries. The UI points helpers to "post it as an item" |
| Needs cannot be edited or deleted from the UI | The API has `DELETE /needs/{id}`, but `api.js` has no wrapper and **My requests** is read-only. `FULFILLED`/`CLOSED` statuses are unreachable |
| Listing detail shows only the first image | Extra images are uploaded and stored but not displayed (`DetailPage`) |
| No way to renew a listing | Expires after 30 days; must be reposted |
| Owners can edit only the price | By design: everything else is locked once posted. To change anything else, delete and repost |
| Email is limited to a welcome message and an admin alert | By design. Sellers and buyers are told of enquiries, replies and messages through the bell only, so someone who never opens the site learns nothing. Google sign-up gets no welcome email |
| The bell is behind the menu button on phones | `NotificationBell` sits in the header's account area, which collapses into the hamburger menu at phone width |
| Chat is polled, not pushed | The open chat asks every 4 s (the bell every 30 s). Fine at this scale; many simultaneous chats would need WebSockets and shared state. No attachments, and messages cannot be edited or deleted |
| Removal notices are owner-only | An admin deleting an item, the expiry cleanup and deactivating a member remove enquiries without telling the people in them |
| Gmail-only registration by default | Configurable via `ALLOWED_EMAIL_DOMAINS` |

## Correctness and robustness issues (Verified in code)

| # | Issue | Where | Impact |
| --- | --- | --- | --- |
| 1 | **Admin delete of a listing does not delete its Cloudinary images** | `routers/admin.py` `admin_delete_listing` | Orphaned assets keep consuming storage; owner delete and expiry cleanup *do* delete them |
| 2 | **Owner delete is not resilient to Cloudinary errors** | `routers/listings.py` `delete_listing` calls `delete_image` without a `try` | A Cloudinary failure returns `500` and the listing stays; cleanup, by contrast, logs and continues |
| 3 | **Login succeeds for deactivated users** | `routers/auth.py` | A token is issued, then every protected call fails with `403`; the SPA would show a logged-in shell that errors. Checking `is_active` at login would give a clearer message |
| 5 | **Non-active listings are publicly readable by ID** | `get_listing_detail` only hides *expired ACTIVE* rows | `SOLD`/`RENTED`/`UNAVAILABLE` (including admin-unlisted) listings remain visible to anyone who knows the ID |
| 7 | **Duplicate-guard returns `201` with the existing record** | `create_listing`, `create_need` | Harmless but surprising; clients cannot tell a replay from a new record |
| 8 | **Registration reveals whether an email/phone exists** (`409` messages) | `routers/auth.py` | Account enumeration; mitigated only by the 5/min/IP limit |
| 9 | **Search wildcards are not escaped** | `ILIKE f"%{search}%"` | `%` and `_` in input act as wildcards (not an injection risk) |
| 10 | **Naive UTC timestamps via `datetime.utcnow()`** | models, routers, cleanup | Deprecated since Python 3.12 (warnings are filtered in `pytest.ini`); API output has no timezone designator |
| 11 | **Unreachable enum values** | `NeedStatus.FULFILLED`/`CLOSED` can never be set through the API | Cosmetic |
| 12 | **Admin status change takes `status` as a query parameter** | `change_listing_status` | Works (the SPA does it) but unusual for a `PATCH`; the status shows in access logs |

## Security and scaling caveats

| Topic | Detail |
| --- | --- |
| JWT in `localStorage` | Any XSS would expose tokens; tokens are valid up to 7 days with no revocation, refresh or logout endpoint (documented in the threat model) |
| CSP is report-only | `CSP_ENFORCE = false`; no `report-uri`/`report-to`, so violations are only visible in the browser console of whoever triggers them |
| In-memory rate limits | Per process, reset on restart, not shared across up to 3 instances (documented). Public detail endpoints and `/auth/me` are unlimited |
| **Possible rate-limit/IP spoofing** — *Inference / verify* | The container starts Uvicorn with `--proxy-headers --forwarded-allow-ips '*'`. With `*` Uvicorn trusts every `X-Forwarded-For` hop, and as far as I recall it then uses the **first (client-supplied) entry** as `request.client.host`. If so, a caller can rotate fake addresses to evade per-IP limits and falsify the IP stored in `audit_logs`/security logs. The per-account login limiter is unaffected. Verify against the deployed service and Uvicorn's current behaviour, and consider trusting only Google's front end or deriving the IP from the right-most forwarded entry |
| **HSTS not observed on the live API** | The deploy workflow sets `HSTS_ENABLED=true`, but a live response on 2026-11-12 carried no `Strict-Transport-Security` header. Check the running revision's environment ([Operations](Operations-and-Troubleshooting.md#live-deployment-snapshot)) |
| No MFA, no account lockout, no breached-password check | Passwords only need a letter and a digit |
| No malware scanning or moderation of uploaded images | Documented |
| Background jobs inside web instances | The expiry cleanup (daily) and the enquiry maintenance job (hourly: 7-day pending expiry, 48-hour reminder) run in each instance's lifespan. With request-based CPU allocation or scale-to-zero they may not run on schedule, so reminders and expiries slip (*Inference*). `run_cleanup.py` runs both once; prefer a scheduled job for it. On PostgreSQL the maintenance job takes an advisory lock so several instances do not duplicate reminders; that branch cannot be tested on SQLite |
| **Startup migrations and background jobs run in every environment** | `main.py` lifespan | `ENVIRONMENT=production` only makes a *failed* migration fatal. A developer machine whose `backend/.env` holds the production URLs applies migrations and runs the cleanup and maintenance jobs against production on every start, and `uvicorn --reload` repeats that on each saved `.py` file. Keep production URLs out of `.env`; consider an opt-in setting for migrations and jobs outside production |
| Three migration tests open a real connection | `tests/conftest.py` does not override `DATABASE_URL_UNPOOLED` | `TC-SVC-MIG-004` to `006` call `apply_migrations()` with `upgrade` patched but still open an engine and take an advisory lock on whatever `.env` names. Run pytest with `DATABASE_URL_UNPOOLED=""` until this is fixed |
| Email addresses are not verified | Anyone can register an address they do not own, which triggers a welcome email to it (limited by the 5/min/IP register limit). Failed emails keep the recipient and body for up to 30 days |
| Audit coverage | Only admin actions are audited (now including retrying or discarding a failed email). Owner deletions, deal closures, interest decisions, reports, blocks and contact reveals are not recorded in `audit_logs` (some appear in logs) |
| Pages deployment branch | The Pages workflow always deploys with `--branch=deploy/neon-cloudrun-cloudflare-pages`; depending on the Pages project's production-branch setting this may be a *preview* deployment (*Inference / verify*) |
| Sync SQLAlchemy in threadpool | Fine at this scale; heavy traffic would need tuning of pools and thread limits |

## Documentation inconsistencies

| Where | Problem |
| --- | --- |
| [backend/.env.example](../backend/.env.example) | Omits `REFERRER_POLICY`, `PERMISSIONS_POLICY`, `API_CSP`; default `CORS_ORIGINS=http://localhost:4200` doesn't match Vite's port 5173 (harmless because of the proxy) |
| Repository meta | No `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` or issue/PR templates |
| Tests | No frontend tests; backend tests don't cover listing creation with images, interests lifecycle transitions beyond contact access, needs endpoints, admin mutations/audit logging, cleanup, or migrations |

## Suggested priorities

1. Delete Cloudinary images on admin listing deletion; wrap owner-delete image removal in error handling.
2. Verify and, if confirmed, fix client-IP derivation behind Cloud Run.
3. Reject or message deactivated users at login.
4. Add length/consistency validation to `ListingUpdate`; wire edit/status-change UI or remove the endpoint.
5. Add pagination (or a higher default limit) to "mine" lists.
6. Run cleanup as a scheduled job.
7. Enforce the SPA CSP after burn-in; consider HttpOnly-cookie sessions or shorter-lived tokens with refresh.
8. Fix the remaining doc gap above and add tests for the gaps.
