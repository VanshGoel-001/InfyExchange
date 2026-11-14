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
| `ListingStatus` | `ACTIVE` (shown as **Available**), `SOLD`, `RENTED` (shown as **Lent out**), `UNAVAILABLE` (admin only) |
| `InterestStatus` | `PENDING` (**Pending**), `ACCEPTED` (**Chatting**), `REJECTED` (**Declined**), `CLOSED` (**Closed**). The stored names are unchanged for backward compatibility; the SPA maps them to words in `src/utils/labels.js` |
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
| PUT | `/api/listings/{id}` | owner | `action` (per user) | Change the price (the only editable field) |
| POST | `/api/listings/{id}/mark-returned` | owner | `action` (per user) | A lent-out item is back: Available again |
| DELETE | `/api/listings/{id}` | owner | – | Delete listing + images |
| POST | `/api/interests/listing/{listing_id}` | user | `create-interest` | Express interest |
| GET | `/api/interests/received` | user | – | Interests on my listings |
| GET | `/api/interests/sent` | user | – | Interests I sent |
| PATCH | `/api/interests/{id}/accept` | listing owner | – | Accept (opens a chat) |
| PATCH | `/api/interests/{id}/reject` | listing owner | – | Decline, with an optional quick reply |
| POST | `/api/interests/{id}/close-deal` | listing owner | `action` (per user) | Sold / rented / lent / given to this person |
| POST | `/api/interests/{id}/still-available` | listing owner | `action` (per user) | Answer the 48-hour reminder |
| POST | `/api/interests/{id}/received` | the buyer | `action` (per user) | Optional "Did you get it?" answer |
| GET | `/api/interests/{id}/contact` | participant | `contact` | Reveal counterparty contact |
| GET | `/api/interests/{id}/chat` | participant | `poll` (per user) | Chat state + messages newer than `after_id` (marks theirs read) |
| POST | `/api/interests/{id}/messages` | participant | `chat` (per user) | Send a message |
| POST | `/api/interests/{id}/report` | participant | `action` (per user) | Report the other person to admins |
| POST / DELETE | `/api/interests/{id}/block` | participant | `action` (per user) | Block / unblock the other person |
| GET | `/api/notifications` | user | `poll` (per user) | Bell: newest notifications + unread count |
| POST | `/api/notifications/read-all`, `/api/notifications/{id}/read` | user | `action` (per user) | Mark read |
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
| GET | `/api/admin/reports` | admin | `admin` | Chat reports from users |
| GET | `/api/admin/failed-emails` | admin | `admin` | Emails the provider refused |
| POST | `/api/admin/failed-emails/{id}/retry` | admin | `admin` | Send a failed email again |
| DELETE | `/api/admin/failed-emails/{id}` | admin | `admin` | Discard a failed email |
| GET | `/api/admin/audit-logs` | admin | `admin` | Read audit trail |

Rate-limit buckets are keyed by `<scope>:<client IP>`, except those marked *per user*, which are keyed by the signed-in account (many trainees share one campus address); see [Rate limits](#rate-limits) for numbers.

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
| `phone` | An Indian mobile number. Spaces, hyphens and a leading `+91` are stripped, then it must match `^[6-9][0-9]{9}$` (ASCII digits only). Stored as the bare 10 digits. 15-digit, 12-digit (`91…` without `+`), wrong-prefix and non-ASCII-digit input is a `422` |
| `password` | 8–100 chars, ≥1 letter and ≥1 digit |
| `role` | `UserRole` |
| `joining_date` | ISO date |

Errors: `400` disallowed domain · `409 Email already registered` · `409 Phone number already registered` · `409 Email or phone number already registered` (two simultaneous registrations; the unique constraint caught the second) · `422` validation · `429` rate limit.

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

Body: `{"phone": "9876543210", "role": "DSE", "joining_date": "2026-01-15"}`. `phone` follows the same Indian-mobile rule as registration (stripped, then `^[6-9][0-9]{9}$`), `joining_date` must not be in the future, unknown fields are rejected (`422`). `409` if the profile is already complete or the phone belongs to someone else. Until this succeeds, creating a listing, need or interest returns `403 Please complete your profile first.`

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
| `title` | string | 2–150 (at least 2 characters once surrounding spaces are removed; `422 title: …` otherwise) |
| `category` | `ListingCategory` | required |
| `listing_type` | `ListingType` | required |
| `price` | int | 0 to 10 000 000, default 0 |
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

Owner only (`403 You can only edit your own listing`). Body: `{"price": 450}` and nothing else. **The price is the only thing an owner can change after posting**; any other field (`title`, `status`, `location`, …) is a `422`, not silently ignored.

- `price` is a whole number from 1 to 10 000 000.
- Only an `ACTIVE` item can be edited (`400 Only available items can be edited`).
- Only `SELL` and `RENT` items have a price (`400 Free items have no price to change`).
- A real change notifies, in the app only, every buyer whose enquiry is `ACCEPTED` (chatting). An unchanged price is a no-op.

### `POST /api/listings/{id}/mark-returned` → `ListingResponse`

Owner only. For a `RENTED` (lent-out) item (`400 This item is not out on loan` otherwise): sets the listing back to `ACTIVE`, stamps `returned_at` on the enquiry the deal was closed with and notifies that borrower. If the listing's 30 days ran out during the loan, `expires_at` is renewed so the Available item does not vanish from search.

### `DELETE /api/listings/{id}` → `{"message": "Listing deleted successfully"}`

Owner only. First notifies (in the app) everyone with a `PENDING` or `ACCEPTED` enquiry, or who is currently borrowing the item, that it was removed; then deletes each Cloudinary image and the row (cascading images, enquiries and chat messages). An admin deleting a listing does **not** send these notices.

---

## Interests

### `POST /api/interests/listing/{listing_id}` → `201 InterestResponse`

Body: `{"message": "optional, ≤500 chars"}`.

`404` listing missing · `400` own listing · `400 This listing is no longer active` (status ≠ `ACTIVE`) · `400 This listing has expired` · `409 You already showed interest` (unique per listing + user; also when two identical submissions race). A person whose earlier enquiry is `CLOSED` is not blocked: that same row is reopened as `PENDING` (new message, `created_at` and `last_activity_at` reset, deal fields cleared) and the response is `201`. `PENDING`, `ACCEPTED` and `REJECTED` enquiries still give `409`.

### `GET /api/interests/received` / `GET /api/interests/sent` → `InterestResponse[]`

`received` = interests on listings I own; `sent` = interests I created. Each item carries `listing_title`, `listing_image_url`, `interested_user_name`, `interested_user_role`.

### `GET /api/interests/received` and `/sent` additions

Each item also carries `listing_type`, `listing_status`, `decline_reply`, `deal_closed_at`, `returned_at`, `received_confirmed` and `unread_count` (messages from the other person this user has not opened).

### `PATCH /api/interests/{id}/accept` → `InterestResponse`

Only the **listing owner** (`403`), only while `PENDING` (`400`), and only while the item is still `ACTIVE` (`400 This item is no longer available`). Sets `ACCEPTED` ("Chatting") and tells the buyer in the app. The listing stays Available and other enquiries are untouched, so an owner can chat with several people at once.

### `PATCH /api/interests/{id}/reject` → `InterestResponse`

Owner only, `PENDING` only. Optional body `{"reply": "…"}` (≤ 200 chars, blank = none); **no body is fine** (one-tap decline). The reply is stored as `decline_reply`, shown to the buyer and included in their notification.

### `POST /api/interests/{id}/close-deal` → `InterestResponse`

Owner only, for an `ACCEPTED` enquiry on an `ACTIVE` item (`400` otherwise). Sets the listing to `SOLD` (sell / giveaway) or `RENTED` (rent / lend); sets this enquiry `CLOSED` with `deal_closed_at`; sets every other `PENDING` or `ACCEPTED` enquiry on the item to `CLOSED` (without `deal_closed_at`) and tells those buyers it is no longer available. The listing row is locked (`SELECT … FOR UPDATE`) so two simultaneous closes cannot both win.

### `POST /api/interests/{id}/still-available` → `InterestResponse`

Owner only, `ACCEPTED` only. Resets `last_activity_at` and clears the reminder, so the 48-hour clock starts again.

### `POST /api/interests/{id}/received` → `InterestResponse`

Body `{"received": true|false}`. Only the buyer the deal was closed with (`403`), only after `close-deal` (`400`). Optional and non-blocking: nothing else waits on it. The owner is notified of the answer.

### `GET /api/interests/{id}/contact` → `{"name","email","phone"}`

Allowed while the enquiry is `ACCEPTED` **and** for the one enquiry the deal was closed with (`CLOSED` with `deal_closed_at`), so the two people can still arrange the handover. `403` for pending, declined and closed-out enquiries, and `403 You are not part of this connection` for anyone but the owner and the interested user. This is still the only API route that returns an email or phone number.

---

## Chat

One thread per enquiry, polled (no WebSockets). Open while the enquiry is `ACCEPTED`, and for the deal winner until a lent item is returned; read-only afterwards. Only the two participants may read or write (`403 You are not part of this conversation`).

### `GET /api/interests/{id}/chat?after_id=0` → `ChatState`

One call for the whole screen: the enquiry and item state (`status`, `listing_status`, `price`, `i_am_owner`, `other_name`, `can_send`, `blocked_by_me`, `deal_closed_at`, `returned_at`, `received_confirmed`, `reminder_pending`) plus `messages` with `id > after_id`. With `after_id=0` it returns the newest 200 messages oldest-first; otherwise up to 200 newer ones. Fetching marks the other person's messages as read. It never carries email or phone. `can_send` is false for blocked pairs in **both** directions, and the response never says who blocked whom.

### `POST /api/interests/{id}/messages` → `201 {id, sender_id, body, created_at}`

Body `{"body": "…"}`, 1–1000 characters after trimming. `403 You cannot message this person.` if either side blocked the other; `403 This chat is closed.` when the chat is not open. The recipient gets one bell notification for the first unread message only; further messages while theirs is unread add none.

### `POST /api/interests/{id}/report` → `201`

Body `{"reason": "…"}`, 5–500 characters. Stored for admins (`GET /api/admin/reports`). Reporting changes nothing for the two people.

### `POST` and `DELETE /api/interests/{id}/block`

Blocks or unblocks the other person *in this enquiry*. The block is between two accounts, so it also silences any other chat they share, and it stops that person sending you new enquiries (`403 You cannot send an enquiry for this item.`, deliberately vague). Both calls are idempotent.

---

## Notifications

### `GET /api/notifications?limit=20` → `{"unread_count", "items": [{id, kind, message, interest_id, created_at, read}]}`

`limit` 1–50. `unread_count` counts everything unread, not just the page. Text never contains contact details. `interest_id` is the chat to open (null once the enquiry is gone).

### `POST /api/notifications/read-all` and `POST /api/notifications/{id}/read`

Another user's notification is `404` (not `403`), so ids cannot be probed.

Notification kinds: `enquiry_received`, `enquiry_accepted`, `enquiry_declined`, `enquiry_closed`, `enquiry_expired`, `deal_closed`, `new_message`, `price_changed`, `item_returned`, `listing_removed`, `received_answer`, `completion_reminder`.

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
| `budget` | int 0 to 10 000 000, default 0 |
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
- `PATCH /api/admin/users/{id}` body `{"is_active"?: bool, "is_admin"?: bool}`. An admin cannot set their own `is_admin` to `false` (`400 Cannot revoke your own admin rights.`). An admin also cannot deactivate their own account (`400 Cannot deactivate your own account.`), which would lock them out with no way back through the API. A no-op change writes no audit entry. Audit action: `UPDATE_USER`.

### Listings

- `GET /api/admin/listings?status_filter&search&skip&limit(≤200)` → `{total, items[]}` with owner name/email and `image_count`.
- `PATCH /api/admin/listings/{id}/status?status=<ListingStatus>` – **status is a query parameter, not a body**. Audit: `UPDATE_LISTING_STATUS` with old/new status.
- `DELETE /api/admin/listings/{id}` – removes the row (cascading); audit: `DELETE_LISTING`. *It does not delete the Cloudinary images* (see [Known Limitations](Known-Limitations-and-Gaps.md)).

### Needs

- `GET /api/admin/needs?status_filter&search&skip&limit(≤200)` → `{total, items[]}`.
- `DELETE /api/admin/needs/{id}` – audit: `DELETE_NEED`.

### Reports

`GET /api/admin/reports?skip&limit(≤100)` → `{total, items[]}`, newest first: reporter, reported person (name, email), item title, reason. Read-only, so nothing is audited.

### Failed emails

Emails the provider refused are stored (already rendered) until an admin decides.

- `GET /api/admin/failed-emails?skip&limit(≤100)` → `{total, items[]}`: `to_email`, `subject`, `error`, `attempts`, timestamps.
- `POST /api/admin/failed-emails/{id}/retry` sends the stored message again. Success deletes the row. A repeat failure is `502`, raises `attempts` and keeps the row. With no provider configured it is `409` and the row is kept (the console adapter would otherwise "succeed" and lose it). Audit action `RETRY_EMAIL` (details: subject and `sent`/`failed`, never the address).
- `DELETE /api/admin/failed-emails/{id}` discards it. Audit action `DISCARD_EMAIL`.
- Unresolved rows are removed by the daily cleanup after 30 days (they hold an address and a message body).

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
| `chat` | `RATE_LIMIT_CHAT` | 30 | `chat-send:user:<id>` | sending chat messages |
| `action` | `RATE_LIMIT_ACTION` | 30 | `<action>:user:<id>` (one bucket per action: `close-deal`, `still-available`, `received`, `edit-listing`, `mark-returned`, `report`, `block`, `notifications-read`) | deal/enquiry state changes, reports, blocks, price edits, mark-read |
| `poll` | `RATE_LIMIT_POLL` | 90 | `chat-poll:user:<id>`, `notifications:user:<id>` | chat and bell polling (the SPA polls the chat every 4 s and the bell every 30 s) |

Not rate-limited: `/health`, `/auth/me`, the `/me` lists, listing/need detail, accept/reject, delete.

The client IP is `request.client.host`. Uvicorn runs with `--proxy-headers --forwarded-allow-ips '*'`, so behind Cloud Run this is the original caller IP from the forwarded headers.

## Response headers

Every response carries `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, and `X-Request-ID`. JSON routes also get a strict API CSP; `/api/auth*`, `/api/users/me*`, `/api/interests*`, `/api/notifications*`, `/api/admin*` get `Cache-Control: no-store`; HSTS is added when `HSTS_ENABLED=true`. Details in [Security](Security.md).
