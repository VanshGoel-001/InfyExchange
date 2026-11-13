# API Reference

Base path: every business route is under **`/api`**. In development the SPA reaches it through the Vite proxy (`/api` → `http://127.0.0.1:8000`); in production the SPA calls `https://<api-host>/api/...`.

Interactive docs: `/docs` (Swagger UI), `/redoc`, `/openapi.json` – **available only when `ENVIRONMENT` is not `production`**.

## Conventions

| Topic | Behaviour |
| --- | --- |
| Auth | `Authorization: Bearer <JWT>`. Obtain a token from `POST /api/auth/login`. Missing header → `403`/`401` from `HTTPBearer`; invalid/expired token → `401 Invalid or expired token`. |
| Deactivated user | Any protected call returns `403 Account is deactivated. Contact an administrator.` (the login endpoint itself still issues a token – see [Known Limitations](Known-Limitations-and-Gaps.md)). |
| Admin | Routes under `/api/admin` require `is_admin`; otherwise `403 Administrative privileges required.` |
| Content type | JSON bodies, except `POST /api/listings` which is `multipart/form-data`. |
| Validation errors | `422` with `{"detail": "<msg>"}` for one error or `{"detail": ["field: msg", ...]}` for several. |
| Server errors | `500` with a generic `detail`; internals are logged, never returned. |
| Pagination | `skip` (≥0, default 0) and `limit` (default 20 for public/user lists, 50 for admin lists; max 100, or 200 for most admin lists, 100 for audit logs). No total count on public lists. |
| Ordering | Newest first (`created_at DESC`). |
| Timestamps | Naive UTC datetimes serialised as ISO-8601 strings without a timezone suffix. |
| Correlation | Send `X-Request-ID` (`[A-Za-z0-9_.-]{1,64}`) to choose your own ID; otherwise one is generated. Always echoed back in the response header. |
| Rate limiting | Exceeding a limit returns `429` with `Retry-After: <window seconds>`. See [Rate limits](#rate-limits). |

## Enumerations

| Enum | Values |
| --- | --- |
| `UserRole` | `SE`, `DSE`, `SP_L1`, `SP_L2` |
| `ListingType` | `SELL`, `RENT`, `LEND`, `GIVEAWAY` |
| `ListingCategory` (also used by needs) | `BADMINTON`, `TABLE_TENNIS`, `POOL_SNOOKER`, `SQUASH`, `TENNIS`, `CRICKET`, `FOOTBALL`, `BASKETBALL`, `OTHER` |
| `ItemCondition` | `NEW`, `LIKE_NEW`, `GOOD`, `FAIR`, `POOR` |
| `ListingStatus` | `ACTIVE`, `SOLD`, `RENTED`, `UNAVAILABLE` |
| `InterestStatus` | `PENDING`, `ACCEPTED`, `REJECTED` |
| `NeedType` | `BUY`, `RENT`, `BORROW` |
| `NeedStatus` | `ACTIVE`, `FULFILLED`, `CLOSED` |

## Endpoint summary

| Method | Path | Auth | Rate-limit bucket | Purpose |
| --- | --- | --- | --- | --- |
| GET | `/` | – | – | Liveness banner |
| GET | `/health` | – | – | Health check (used by Docker `HEALTHCHECK` and the deploy workflow) |
| POST | `/api/auth/register` | – | `register` (IP) | Create account |
| POST | `/api/auth/login` | – | `login` (IP) + per-account | Obtain JWT |
| POST | `/api/auth/google` | – | `login` (IP) | Sign in / sign up with a Google ID token |
| GET | `/api/auth/me` | user | – | Current user |
| GET | `/api/users/me` | user | – | Current user (same payload) |
| POST | `/api/users/me/complete-profile` | user | – | One-time phone, role, joining date for Google-created accounts |
| PATCH | `/api/users/me` | user | – | Change role and/or joining date |
| GET | `/api/users/me/summary` | user | – | Activity counters |
| POST | `/api/listings` | user | `create-listing` | Create listing (+ images) |
| GET | `/api/listings` | – | `read-listings` | Search active listings |
| GET | `/api/listings/me` | user | – | My listings (any status) |
| GET | `/api/listings/{id}` | – | – | Listing detail |
| PUT | `/api/listings/{id}` | owner | – | Edit listing |
| DELETE | `/api/listings/{id}` | owner | – | Delete listing + images |
| POST | `/api/interests/listing/{listing_id}` | user | `create-interest` | Express interest |
| GET | `/api/interests/received` | user | – | Interests on my listings |
| GET | `/api/interests/sent` | user | – | Interests I sent |
| PATCH | `/api/interests/{id}/accept` | listing owner | – | Accept |
| PATCH | `/api/interests/{id}/reject` | listing owner | – | Reject |
| GET | `/api/interests/{id}/contact` | participant | `contact` | Reveal counterparty contact |
| POST | `/api/needs` | user | `create-need` | Create need |
| GET | `/api/needs` | – | `read-needs` | Search active needs |
| GET | `/api/needs/me` | user | – | My needs |
| GET | `/api/needs/{id}` | – | – | Need detail |
| DELETE | `/api/needs/{id}` | owner | – | Delete need |
| GET | `/api/admin/stats` | admin | `admin` | Platform counters |
| GET | `/api/admin/users` | admin | `admin` | List/search users |
| PATCH | `/api/admin/users/{id}` | admin | `admin` | Activate/deactivate, grant/revoke admin |
| GET | `/api/admin/listings` | admin | `admin` | List/search all listings |
| PATCH | `/api/admin/listings/{id}/status` | admin | `admin` | Set listing status |
| DELETE | `/api/admin/listings/{id}` | admin | `admin` | Remove listing |
| GET | `/api/admin/needs` | admin | `admin` | List/search all needs |
| DELETE | `/api/admin/needs/{id}` | admin | `admin` | Remove need |
| GET | `/api/admin/audit-logs` | admin | `admin` | Read audit trail |

Rate-limit buckets are keyed by `<scope>:<client IP>`; see [Rate limits](#rate-limits) for numbers.

---

## Authentication

### `POST /api/auth/register` → `201 UserResponse`

```json
{
  "name": "Asha Rao",
  "email": "asha@gmail.com",
  "phone": "9876543210",
  "password": "Passw0rd1",
  "role": "SE",
  "joining_date": "2026-01-05"
}
```

| Field | Rules |
| --- | --- |
| `name` | 2–100 chars (trimmed before saving) |
| `email` | valid email; lower-cased; must end with `@<domain>` for a domain in `ALLOWED_EMAIL_DOMAINS` (default `gmail.com`; an empty setting also falls back to `gmail.com`) |
| `phone` | 10–15 chars (no format check beyond length) |
| `password` | 8–100 chars, ≥1 letter and ≥1 digit |
| `role` | `UserRole` |
| `joining_date` | ISO date |

Errors: `400` disallowed domain · `409 Email already registered` · `409 Phone number already registered` · `422` validation · `429` rate limit.

### `POST /api/auth/login` → `200 {"access_token": "...", "token_type": "bearer"}`

Body: `{"email": "...", "password": "..."}`. Wrong email and wrong password return the **identical** `401 Invalid email or password`. Two limiters apply (per IP and per hashed account) – see below.

### `GET /api/auth/me` and `GET /api/users/me` → `UserResponse`

```json
{ "id": 1, "name": "...", "email": "...", "phone": "...", "role": "SE",
  "is_admin": false, "is_active": true, "joining_date": "2026-01-05",
  "created_at": "2026-02-01T10:00:00", "profile_complete": true }
```

`password_hash` and `google_sub` are never returned (tested). `phone`, `role` and `joining_date` are `null` and `profile_complete` is `false` for a Google-created account that has not finished the profile step.

### `POST /api/auth/google` → `200 {"access_token": "...", "token_type": "bearer"}`

Body: `{"credential": "<Google ID token>"}` (1–4096 chars). The token is verified server-side: RS256 signature against Google's published keys (algorithm pinned), `aud` equal to `GOOGLE_CLIENT_ID`, issuer `accounts.google.com`, expiry (10 s leeway) and `email_verified`. Then:

- A known Google account id (`sub`) signs in. A new one creates a user with `name`/`email` from Google and no password, phone, role or joining date.
- The email must pass the same `ALLOWED_EMAIL_DOMAINS` rule as registration (`400`).
- An email that already belongs to a **password** account is refused (`409 An account with this email already exists. Please log in with your password.`). Accounts are never merged automatically, because registration does not prove mailbox ownership.
- Deactivated users get `403`.

Errors: `401 Google sign-in failed. Please try again.` (any bad credential, deliberately generic) · `503` when `GOOGLE_CLIENT_ID` is empty or Google's keys cannot be fetched · `422` · `429` (shares the `login` bucket).

### `POST /api/users/me/complete-profile` → `200 UserResponse`

Body: `{"phone": "9876543210", "role": "DSE", "joining_date": "2026-01-15"}`. `phone` must be 10–15 **digits**, `joining_date` must not be in the future, unknown fields are rejected (`422`). `409` if the profile is already complete or the phone belongs to someone else. Until this succeeds, creating a listing, need or interest returns `403 Please complete your profile first.`

### `PATCH /api/users/me` → `200 UserResponse`

Body: `role` and/or `joining_date` (at least one). Name, email and phone are not editable: any other field is a `422`. `409` while the profile is incomplete.

### `GET /api/users/me/summary` → `UserActivitySummary`

`my_listings_count`, `my_needs_count`, `my_interests_count` (sent), `requests_received_count`, `pending_requests_received_count`.

---

## Listings

### `POST /api/listings` → `201 ListingDetailResponse`

`multipart/form-data` fields:

| Field | Type | Rules |
| --- | --- | --- |
| `title` | string | 2–150 |
| `category` | `ListingCategory` | required |
| `listing_type` | `ListingType` | required |
| `price` | int | ≥0, default 0 |
| `price_unit` | string | ≤30; only meaningful for `RENT` |
| `condition` | `ItemCondition` | required |
| `location` | string | 2–100 |
| `description` | string | 2–2000 |
| `images` | file[] | ≤ `MAX_IMAGES_PER_LISTING` (5); JPEG/PNG/WebP; ≤ `MAX_IMAGE_SIZE_MB` (5) each; magic-byte checked |

Server-side rules (verified in `routers/listings.py`):

- `LEND` and `GIVEAWAY` force `price = 0` and `price_unit = null`.
- `SELL` and `RENT` require `price > 0` (`400`).
- `RENT` without `price_unit` defaults to `"day"`.
- **Duplicate guard:** same owner + title + type + price + location + description within `DUPLICATE_SUBMISSION_WINDOW_SECONDS` (60) returns the existing listing instead of creating another (still HTTP 201).
- `expires_at = now + LISTING_EXPIRY_DAYS` (30 days).
- If any image fails, uploaded images are deleted, the listing is deleted, and the response is `400 Failed to upload images. Please try again.`

### `GET /api/listings` → `ListingResponse[]`

Public. Only `ACTIVE`, non-expired listings.

| Query | Type | Matching |
| --- | --- | --- |
| `search` | string | case-insensitive substring of **title** |
| `category`, `listing_type`, `condition` | enum | exact |
| `location` | string | case-insensitive substring |
| `min_price`, `max_price` | int ≥0 | inclusive bounds |
| `skip`, `limit` | int | `limit` 1–100, default 20 |

`ListingResponse` adds `owner_name`, `owner_role`, and `image_url` (the first image by lowest `id`).

### `GET /api/listings/me` → `ListingResponse[]`

Own listings in **all** statuses, including expired ones not yet cleaned up. Only `skip`/`limit`; the SPA filters client-side.

### `GET /api/listings/{id}` → `ListingDetailResponse`

Public, and **not limited to `ACTIVE`**: `SOLD`/`RENTED`/`UNAVAILABLE` listings are still returned by ID. Returns `404 Listing has expired` only when status is `ACTIVE` and `expires_at` has passed. Includes `images: [{id, image_url}]`.

### `PUT /api/listings/{id}` → `ListingResponse`

Owner only (`403 You can only edit your own listing`). Body (all optional): `title` (2–150), `price` (≥0), `price_unit`, `condition`, `location`, `description`, `status`. Only supplied fields are changed. Note that the owner can set `status` to any `ListingStatus`, and that `price`/`location`/`description` are not re-validated against the create rules. The bundled SPA does not call this endpoint.

### `DELETE /api/listings/{id}` → `{"message": "Listing deleted successfully"}`

Owner only. Deletes each Cloudinary image, then the row (cascading images and interests).

---

## Interests

### `POST /api/interests/listing/{listing_id}` → `201 InterestResponse`

Body: `{"message": "optional, ≤500 chars"}`.

`404` listing missing · `400` own listing · `400 This listing is no longer active` (status ≠ `ACTIVE`) · `400 This listing has expired` · `409 You already showed interest` (unique per listing + user).

### `GET /api/interests/received` / `GET /api/interests/sent` → `InterestResponse[]`

`received` = interests on listings I own; `sent` = interests I created. Each item carries `listing_title`, `listing_image_url`, `interested_user_name`, `interested_user_role`.

### `PATCH /api/interests/{id}/accept` and `/reject` → `InterestResponse`

Only the **listing owner** (`403`) and only while `PENDING` (`400 Only pending interests can be accepted/rejected`). Transitions are final – there is no way back to `PENDING`.

### `GET /api/interests/{id}/contact` → `{"name","email","phone"}`

`403` unless the interest is `ACCEPTED`; `403 You are not part of this connection` for anyone other than the listing owner or the interested user. The owner receives the interested user's details; the interested user receives the owner's.

---

## Needs

### `POST /api/needs` → `201 NeedResponse`

JSON body:

| Field | Rules |
| --- | --- |
| `title` | 2–150 |
| `category` | `ListingCategory` |
| `need_type` | `BUY` / `RENT` / `BORROW` |
| `duration` | optional, ≤100 (free text, e.g. "2 weeks") |
| `budget` | int ≥0, default 0 |
| `location` | 2–100 |
| `description` | 2–2000 |

Duplicate guard (60 s, same user/title/type/budget/location/description) returns the existing record. Expiry uses `LISTING_EXPIRY_DAYS` (30). Response includes `user_name`.

### `GET /api/needs` → `NeedResponse[]`

Public; active and non-expired only. Filters: `search` (title substring), `category`, `need_type`, `location` (substring), `skip`, `limit`.

### `GET /api/needs/me`, `GET /api/needs/{id}`, `DELETE /api/needs/{id}`

`/me` lists the caller's needs. `{id}` is public (`404 Need has expired` for expired-but-active). `DELETE` is owner only (`403 You can only delete your own need`). There is no update endpoint for needs.

---

## Admin (`/api/admin/*`)

The router-level dependencies run `get_current_admin` and the `admin` rate limiter for **every** admin route.

### `GET /api/admin/stats`

`total_users`, `active_users`, `total_listings`, `active_listings`, `total_needs`, `active_needs`, `total_interests`, `accepted_interests`.

### Users

- `GET /api/admin/users?skip&limit(≤200)&search` → `{total, items[]}`; search matches name or email (case-insensitive substring). Items include email, phone, role, flags, `joining_date`, `created_at`.
- `PATCH /api/admin/users/{id}` body `{"is_active"?: bool, "is_admin"?: bool}`. An admin cannot set their own `is_admin` to `false` (`400 Cannot revoke your own admin rights.`). A no-op change writes no audit entry. Audit action: `UPDATE_USER`.

### Listings

- `GET /api/admin/listings?status_filter&search&skip&limit(≤200)` → `{total, items[]}` with owner name/email and `image_count`.
- `PATCH /api/admin/listings/{id}/status?status=<ListingStatus>` – **status is a query parameter, not a body**. Audit: `UPDATE_LISTING_STATUS` with old/new status.
- `DELETE /api/admin/listings/{id}` – removes the row (cascading); audit: `DELETE_LISTING`. *It does not delete the Cloudinary images* (see [Known Limitations](Known-Limitations-and-Gaps.md)).

### Needs

- `GET /api/admin/needs?status_filter&search&skip&limit(≤200)` → `{total, items[]}`.
- `DELETE /api/admin/needs/{id}` – audit: `DELETE_NEED`.

### Audit log

`GET /api/admin/audit-logs?skip&limit(≤100)` → `{total, items[]}`, newest first. Each item: `id`, `actor_id`, `actor_name` (`"System"` when the actor was deleted), `action`, `target_type`, `target_id`, `ip_address`, `details` (JSON string), `created_at`.

Audit entries are written through `log_admin_action`, which `flush`es in the same transaction as the change and **swallows its own errors** (logged only) so an audit failure never blocks an admin action.

---

## Rate limits

Defaults from `config.py`; window `RATE_LIMIT_WINDOW_SECONDS` = 60 s. Sliding window, in memory, **per API process**.

| Limiter | Env var | Default | Key | Applied to |
| --- | --- | --- | --- | --- |
| `login` | `RATE_LIMIT_LOGIN` | 10 | `login:<ip>` | `POST /auth/login` |
| `login-account` | `RATE_LIMIT_LOGIN` | 10 | `acct:<sha256(email)[:32]>` | `POST /auth/login` |
| `google` | `RATE_LIMIT_LOGIN` | 10 | `google:<ip>` | `POST /auth/google` |
| `register` | `RATE_LIMIT_REGISTER` | 5 | `register:<ip>` | `POST /auth/register` |
| `create` | `RATE_LIMIT_CREATE` | 10 | `create-listing:<ip>`, `create-need:<ip>`, `create-interest:<ip>` | the three create endpoints (separate bucket each) |
| `read` | `RATE_LIMIT_READ` | 120 | `read-listings:<ip>`, `read-needs:<ip>` | the two public list endpoints |
| `contact` | `RATE_LIMIT_CONTACT` | 20 | `contact:<ip>` | contact reveal |
| `admin` | `RATE_LIMIT_ADMIN` | 60 | `admin:<ip>` | all admin routes |

Not rate-limited: `/health`, `/auth/me`, the `/me` lists, listing/need detail, accept/reject, update/delete.

The client IP is `request.client.host`. Uvicorn runs with `--proxy-headers --forwarded-allow-ips '*'`, so behind Cloud Run this is the original caller IP from the forwarded headers.

## Response headers

Every response carries `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, and `X-Request-ID`. JSON routes also get a strict API CSP; `/api/auth*`, `/api/users/me*`, `/api/interests*`, `/api/admin*` get `Cache-Control: no-store`; HSTS is added when `HSTS_ENABLED=true`. Details in [Security](Security.md).
