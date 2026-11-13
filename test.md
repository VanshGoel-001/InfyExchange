# test.md - Test Plan for InfyExchange

> **Status: executed 2026-11-12/13.** The first full run of the suite gave 490 passed and 1 failed; the failure was a bug in the test itself (`TC-API-ADM-052` read an ORM object after the API had deleted its row) and is fixed. The latest full run, including the Google sign-in and profile tests added in [section 17](#17-additions-google-sign-in-and-profile-editing), is **578 passed, 0 failed** (about 3.5 minutes, SQLite).
>
> **Baseline caveat.** The approved artifacts `constitution.md`, `clarification.md`, `spec.md`, `plan.md`, `data-model.md`, `api-contract.md` and `tasks.md` do not exist for InfyExchange (searched `D:\Asus`, the repository, `InfyExchange - Copy` and the zip). As agreed, a **derived baseline** was reconstructed from the code, `wiki/` and `docs/security/` and is recorded in [Appendix A](#appendix-a---derived-baseline). Every acceptance criterion (AC), functional requirement (FR) and task (T) ID below is **derived, not approved**. When the real artifacts exist, re-map the IDs; the test code itself does not change. No requirement was invented: where behaviour is unclear it is listed under [Open Questions](#16-open-questions) and left untested.

## 1. Purpose of test.md

Defines what is tested, how, in what order and against which requirement, so that the new automated suite and the manual checks can be reviewed, run and traced. It maps each test case to (a) a derived acceptance criterion, (b) an endpoint or service, and (c) an implementation task. The original suite added tests only. The later Google sign-in / profile feature (section 17) did change application code, with its own tests.

## 2. Source artifacts and how they were used

| Requested artifact | Found? | What was used instead |
| --- | --- | --- |
| spec.md (primary source: acceptance criteria) | No | Behaviour read from `backend/app/routers`, `schemas`, `services`, `wiki/Business-Rules-and-Flows.md`; recorded as AC-xx.y in Appendix A |
| api-contract.md (endpoint expectations) | No | `wiki/API-Reference.md` and the route/schema code; endpoint table in Appendix A.3 |
| tasks.md (task mapping) | A different file: the product roadmap in `D:\Asus\infy_exchange_final\tasks.md` | Implementation tasks T01-T16 derived from the backend modules (Appendix A.2) |
| data-model.md | `wiki/Data-Model.md` exists | Used for tables, constraints, cascades |
| constitution.md, clarification.md, plan.md | No (an unrelated `plan.md` exists in `MDD frontend`) | Project rules from `CLAUDE.md` and `docs/security/` (e.g. no contact leakage, ownership checks) |

## 3. Testing Scope

**In scope (automated, backend):** services (settings, password/JWT, rate limiter, image validation, cleanup, migrations), every REST endpoint under `/api`, request validation, data integrity and cascade rules, authorization, throttling, and the admin audit trail.

**In scope (manual):** behaviour that needs real infrastructure: PostgreSQL-specific constraints, Cloudinary, the deployed Cloud Run / Pages stack, scheduled cleanup, and the SPA.

**Existing suites kept as regression:** 43 tests in `test_auth.py`, `test_authorization.py`, `test_input_validation.py`, `test_security_headers.py` (mapped to ACs in section 6; not duplicated).

## 4. Test strategy

| Layer | Tooling | Isolation |
| --- | --- | --- |
| Service tests (`test_service_*.py`) | pytest; direct function calls; `asyncio.run` for async code; fake clock for the limiter; patched Cloudinary | No network; SQLite temp DB (cleanup) or fresh temp file (real Alembic run) |
| Validation tests (`test_validation_schemas.py`) | pytest + Pydantic models directly, plus a few API calls for the 422 contract | None needed |
| API tests (`test_api_*.py`) | FastAPI `TestClient`; users/listings created directly in the DB through helpers; JWTs from `auth_headers` | Each test gets freshly created tables and cleared rate limiters (existing autouse fixture) |
| Data-integrity tests (`test_data_integrity.py`) | SQLAlchemy sessions against the SQLite test DB | Same fixture |
| Manual verification | Checklist in section 11 | Staging environment, synthetic data |

Conventions:

- **Traceability:** every new test's first docstring line is `TC-<LAYER>-<AREA>-<NNN> | AC list | task list | kind | description`; this document's tables are generated from those lines. `kind` is `positive`, `negative`, `boundary` or `business`.
- **Reuse:** `tests/conftest.py` fixtures (`client`, `db_session`, `make_user`, `auth_headers`, `register_payload`) are reused unchanged; new builders live in `tests/support.py`.
- **Cloudinary** is never called. Router tests patch `app.routers.listings.upload_image/delete_image` with `FakeCloudinary`; cleanup tests patch `app.services.cleanup.delete_image`; image-service tests patch `cloudinary.uploader.upload/destroy`.
- **Throttle tests** lower the relevant limiter's `max_requests` with `monkeypatch` instead of sending hundreds of requests; default values are asserted separately (`TC-SVC-CFG-003`).
- **Known SQLite limits:** foreign keys are not enforced by default and PostgreSQL enum types do not exist. ORM-level cascades and unique indexes are tested automatically; DB-level cascade/SET NULL/enums are in the manual section (`TC-MAN-DB-*`).
- **Parametrization** expands the counts below at run time: 277 test functions are defined (44 are parametrized), so the executed count will be higher.

## 5. Requirement-to-test mapping

New automated test functions per functional requirement (existing regression tests and manual checks shown separately).

| FR | Requirement | Acceptance criteria | New automated | Existing | Manual |
| --- | --- | --- | --- | --- | --- |
| FR-01 | User registration | 01.1, 01.2, 01.3, 01.4, 01.5, 01.6 | 29 | 8 | 1 |
| FR-02 | Login and token issuance | 02.1, 02.2, 02.3, 02.4 | 21 | 3 | 1 |
| FR-03 | Authenticated identity and account state | 03.1, 03.2, 03.3 | 16 | 6 | 1 |
| FR-04 | Create listing | 04.1, 04.2, 04.3, 04.4, 04.5, 04.6 | 23 | 0 | 4 |
| FR-05 | Browse and search listings | 05.1, 05.2, 05.3, 05.4, 05.5 | 13 | 2 | 0 |
| FR-06 | Listing detail and my listings | 06.1, 06.2 | 7 | 0 | 0 |
| FR-07 | Owner edit and delete of listings | 07.1, 07.2, 07.3, 07.4 | 16 | 3 | 1 |
| FR-08 | Needs (requests) | 08.1, 08.2, 08.3, 08.4, 08.5, 08.6, 08.7 | 29 | 0 | 0 |
| FR-09 | Interests and owner decisions | 09.1, 09.2, 09.3, 09.4, 09.5 | 28 | 1 | 1 |
| FR-10 | Contact reveal | 10.1, 10.2, 10.3, 10.4 | 9 | 3 | 1 |
| FR-11 | Activity summary | 11.1 | 5 | 0 | 0 |
| FR-12 | Admin moderation | 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7 | 31 | 3 | 1 |
| FR-13 | Admin audit trail | 13.1, 13.2, 13.3 | 10 | 0 | 2 |
| FR-14 | Expiry cleanup | 14.1, 14.2 | 7 | 0 | 2 |
| FR-15 | Rate limiting | 15.1, 15.2 | 12 | 3 | 1 |
| FR-16 | Image validation and storage | 16.1, 16.2 | 13 | 0 | 2 |
| FR-17 | Response security (headers, CORS, request id) | 17.1, 17.2, 17.3, 17.4 | 3 | 10 | 3 |
| FR-18 | Error handling | 18.1, 18.2 | 5 | 1 | 0 |
| FR-19 | Data integrity and migrations | 19.1, 19.2, 19.3, 19.4, 19.5, 19.6 | 30 | 0 | 4 |
| FR-20 | Configuration | 20.1, 20.2, 20.3 | 9 | 0 | 0 |

## 6. Acceptance criteria mapping

Primary mapping (AC -> test IDs). "Existing" lists the pre-existing test function names that already cover the AC.

| AC | Criterion (derived) | New test cases | Existing tests | Manual |
| --- | --- | --- | --- | --- |
| AC-01.1 | Valid registration returns 201 with the profile and no password data. | TC-API-REG-001, TC-API-REG-006 | test_registration_response_has_no_password_hash, test_registration_succeeds_with_strong_password | TC-MAN-FLOW-001 |
| AC-01.2 | Only emails from the allowed domain list (default gmail.com) are accepted; exact, case-insensitive domain match. | TC-API-REG-003, TC-API-REG-007, TC-API-REG-008, TC-API-REG-009, TC-SVC-CFG-012, TC-VAL-REG-004 | test_registration_rejects_disallowed_email_domain | - |
| AC-01.3 | Email and phone must be unique; duplicates return 409. | TC-API-REG-010, TC-API-REG-011, TC-API-REG-012, TC-API-REG-013, TC-DI-UNQ-005 | - | - |
| AC-01.4 | Password is 8-100 characters with at least one letter and one digit, stored as an Argon2id hash. | TC-API-REG-002, TC-DI-VAL-003, TC-SVC-AUT-001, TC-SVC-AUT-002, TC-SVC-AUT-006, TC-SVC-AUT-007, TC-VAL-REG-003 | test_password_hash_uses_argon2id, test_password_policy_rejects_letters_only, test_password_policy_rejects_short_password | - |
| AC-01.5 | Field limits: name 2-100, phone 10-15, valid role and joining date; text is trimmed. | TC-API-REG-004, TC-VAL-REG-001, TC-VAL-REG-002, TC-VAL-REG-005, TC-VAL-REG-006, TC-VAL-REG-007, TC-VAL-REG-008 | test_register_rejects_missing_fields, test_register_rejects_oversized_values | - |
| AC-01.6 | New accounts are non-admin and active; clients cannot set these flags. | TC-API-REG-001, TC-API-REG-005, TC-DI-DEF-001 | - | - |
| AC-02.1 | Valid credentials return a bearer JWT for that user. | TC-API-LOG-001, TC-API-LOG-002, TC-API-REG-006, TC-SVC-AUT-003, TC-SVC-AUT-010, TC-SVC-AUT-011, TC-SVC-AUT-012, TC-SVC-CFG-002 | test_login_success_returns_bearer_token | - |
| AC-02.2 | Invalid credentials return an identical 401 regardless of cause; malformed bodies are 422. | TC-API-LOG-003, TC-API-LOG-008, TC-API-LOG-009, TC-SVC-AUT-004, TC-SVC-AUT-005, TC-VAL-LOG-001, TC-VAL-LOG-002, TC-VAL-LOG-003 | test_login_failure_messages_are_identical | - |
| AC-02.3 | Login email is case-insensitive. | TC-API-LOG-004 | - | - |
| AC-02.4 | Login is throttled per IP and per account (10 per 60 s) with 429 + Retry-After. | TC-API-LOG-005, TC-API-LOG-006, TC-API-LOG-007, TC-SVC-CFG-003 | test_login_rate_limit_returns_429_with_retry_after | TC-MAN-OPS-002 |
| AC-03.1 | /api/auth/me and /api/users/me return the caller's profile. | TC-API-IDN-001, TC-API-LOG-002, TC-SVC-AUT-010 | test_cannot_read_other_users_profile_endpoint, test_profile_response_has_no_password_hash | - |
| AC-03.2 | Missing, malformed, expired, forged or unknown-user tokens are rejected (401/403). | TC-API-IDN-002, TC-API-IDN-003, TC-API-IDN-004, TC-API-IDN-005, TC-SVC-AUT-013, TC-SVC-AUT-014, TC-SVC-AUT-015, TC-SVC-AUT-016, TC-SVC-AUT-017, TC-SVC-AUT-018 | test_alg_none_token_rejected, test_invalid_token_rejected, test_unauthenticated_access_denied | TC-MAN-FLOW-003 |
| AC-03.3 | Deactivated accounts receive 403 on every protected endpoint. | TC-API-ADM-004, TC-API-ADM-025, TC-API-IDN-006 | test_deactivated_user_rejected | - |
| AC-04.1 | Valid listing creation returns 201, status ACTIVE, owned by the caller, expiring after 30 days. | TC-API-LST-001, TC-API-LST-002, TC-DI-DEF-004, TC-SVC-CFG-001 | - | TC-MAN-FLOW-001 |
| AC-04.2 | Pricing: SELL and RENT need price > 0; LEND/GIVEAWAY force price 0 and no unit; RENT defaults unit to 'day'. | TC-API-LST-005, TC-API-LST-006, TC-API-LST-007, TC-API-LST-008, TC-API-LST-009 | - | - |
| AC-04.3 | Field limits: title 2-150, location 2-100, description 2-2000, price >= 0, valid enums; text is trimmed. | TC-API-LST-003, TC-API-LST-010, TC-API-LST-011 | - | TC-MAN-UI-001 |
| AC-04.4 | An identical submission by the same owner within 60 s returns the existing listing. | TC-API-LST-012, TC-API-LST-013, TC-API-LST-014, TC-API-LST-015, TC-SVC-CFG-001 | - | - |
| AC-04.5 | At most 5 images; an upload failure rolls back the listing and removes already-uploaded images. | TC-API-LST-016, TC-API-LST-017, TC-API-LST-018, TC-API-LST-019, TC-DI-VAL-001, TC-SVC-CFG-001 | - | TC-MAN-DB-002, TC-MAN-IMG-001 |
| AC-04.6 | Creation requires authentication and is throttled. | TC-API-LST-004, TC-API-LST-020 | - | - |
| AC-05.1 | Public browse returns only ACTIVE, unexpired listings. | TC-API-LST-030, TC-API-LST-031, TC-API-LST-072 | - | - |
| AC-05.2 | Filters: title search, category, type, condition, location, inclusive price range. | TC-API-LST-032, TC-API-LST-033, TC-API-LST-034 | test_search_input_cannot_break_sql, test_search_input_with_quotes_returns_cleanly | - |
| AC-05.3 | Newest first; skip >= 0; limit 1-100 (default 20). | TC-API-LST-035, TC-API-LST-036, TC-API-LST-037, TC-API-LST-038 | - | - |
| AC-05.4 | List items show owner name/role and first image and never contact details. | TC-API-LST-039 | - | - |
| AC-05.5 | Browse is throttled. | TC-API-LST-040, TC-SVC-CFG-003 | - | - |
| AC-06.1 | Detail returns the listing with images; 404 for unknown or expired-active listings. | TC-API-LST-050, TC-API-LST-051, TC-API-LST-052, TC-API-LST-053 | - | - |
| AC-06.2 | /listings/me returns only the caller's listings (any status) and requires authentication. | TC-API-LST-060, TC-API-LST-061, TC-API-LST-062 | - | - |
| AC-07.1 | The owner can partially update a listing; unspecified fields stay unchanged. | TC-API-LST-070, TC-API-LST-071, TC-API-LST-072, TC-VAL-LST-001, TC-VAL-LST-005 | test_owner_can_update_own_listing | - |
| AC-07.2 | Non-owners get 403, unknown listings 404, anonymous callers 401/403. | TC-API-LST-073, TC-API-LST-082, TC-API-LST-083 | test_horizontal_escalation_listing_delete_blocked, test_horizontal_escalation_listing_update_blocked | - |
| AC-07.3 | Update validation: title 2-150, price >= 0, valid enums. | TC-API-LST-074, TC-VAL-LST-002, TC-VAL-LST-003, TC-VAL-LST-004 | - | - |
| AC-07.4 | Deleting a listing removes its images (including Cloudinary assets) and interests. | TC-API-LST-080, TC-API-LST-081, TC-DI-VAL-001, TC-SVC-IMG-020 | - | TC-MAN-IMG-002 |
| AC-08.1 | Valid need creation returns 201, status ACTIVE, expiring after 30 days. | TC-API-NED-001, TC-API-NED-002, TC-API-NED-004 | - | - |
| AC-08.2 | Need limits: title 2-150, location 2-100, description 2-2000, duration <= 100, budget >= 0, valid enums. | TC-API-NED-003, TC-API-NED-005, TC-API-NED-006, TC-API-NED-007, TC-API-NED-008, TC-VAL-NED-001, TC-VAL-NED-002, TC-VAL-NED-003, TC-VAL-NED-004 | - | - |
| AC-08.3 | An identical need within 60 s returns the existing record. | TC-API-NED-009, TC-API-NED-010 | - | - |
| AC-08.4 | Public need browse returns ACTIVE, unexpired needs with filters, ordering and pagination. | TC-API-NED-020, TC-API-NED-021, TC-API-NED-022, TC-API-NED-023, TC-API-NED-024 | - | - |
| AC-08.5 | /needs/me lists own needs; detail is public; 404 for unknown or expired-active needs. | TC-API-NED-030, TC-API-NED-031, TC-API-NED-032, TC-API-NED-033, TC-API-NED-034 | - | - |
| AC-08.6 | Only the owner can delete a need. | TC-API-NED-040, TC-API-NED-041, TC-API-NED-042 | - | - |
| AC-08.7 | Need creation and browsing are throttled. | TC-API-NED-011, TC-API-NED-025 | - | - |
| AC-09.1 | Expressing interest creates a PENDING interest; message optional, at most 500 characters. | TC-API-INT-001, TC-API-INT-002, TC-API-INT-003, TC-API-INT-011, TC-API-INT-045, TC-DI-DEF-002, TC-VAL-INT-001, TC-VAL-INT-002 | - | TC-MAN-FLOW-001 |
| AC-09.2 | Interest is refused for own, missing, inactive or expired listings and for duplicates (409). | TC-API-INT-004, TC-API-INT-005, TC-API-INT-006, TC-API-INT-007, TC-API-INT-008, TC-API-INT-009, TC-API-INT-010 | test_cannot_show_interest_in_own_listing | - |
| AC-09.3 | Sent and received lists are scoped to the caller, enriched with names/titles, ordered and paginated. | TC-API-INT-020, TC-API-INT-021, TC-API-INT-022, TC-API-INT-023, TC-API-INT-024, TC-API-INT-025 | - | - |
| AC-09.4 | Only the listing owner can accept/reject, and only PENDING interests. | TC-API-INT-030, TC-API-INT-031, TC-API-INT-032, TC-API-INT-033, TC-API-INT-034, TC-API-INT-045 | - | TC-MAN-FLOW-001 |
| AC-09.5 | Accepting does not change the listing or other interests. | TC-API-INT-035, TC-API-INT-036 | - | - |
| AC-10.1 | Contact details are returned only for ACCEPTED interests, only to the two participants, as the counterpart's name, email and phone. | TC-API-INT-040, TC-API-INT-045 | test_contact_details_visible_to_participants | TC-MAN-FLOW-001 |
| AC-10.2 | Contact is refused for pending/rejected interests, non-participants, unknown ids and anonymous callers. | TC-API-INT-041, TC-API-INT-042, TC-API-INT-043 | test_contact_details_blocked_before_acceptance, test_contact_details_blocked_for_third_party | - |
| AC-10.3 | Contact reveal is throttled. | TC-API-INT-044, TC-SVC-CFG-003 | - | - |
| AC-10.4 | Contact details never appear in any other payload. | TC-API-LST-039, TC-API-NED-021 | - | - |
| AC-11.1 | The summary returns accurate listing, need, sent, received and pending-received counters. | TC-API-USR-001, TC-API-USR-002, TC-API-USR-003, TC-API-USR-004, TC-DI-CON-001 | - | - |
| AC-12.1 | Every admin route requires an active admin (403 members, 401/403 anonymous). | TC-API-ADM-001, TC-API-ADM-002, TC-API-ADM-004 | test_admin_endpoints_require_authentication, test_vertical_escalation_admin_stats_blocked | TC-MAN-FLOW-002 |
| AC-12.2 | Stats report total and active counts for users, listings, needs and interests. | TC-API-ADM-010, TC-API-ADM-011 | test_admin_can_access_admin_stats | TC-MAN-FLOW-002 |
| AC-12.3 | Admin user list supports search and pagination (limit 1-200) without secrets. | TC-API-ADM-020, TC-API-ADM-021, TC-API-ADM-022, TC-API-ADM-023 | - | TC-MAN-FLOW-002 |
| AC-12.4 | Admins can activate/deactivate users and grant/revoke admin; self-demotion is refused; unknown user is 404. | TC-API-ADM-024, TC-API-ADM-025, TC-API-ADM-026, TC-API-ADM-027, TC-API-ADM-028, TC-API-ADM-029, TC-API-ADM-030, TC-API-ADM-032 | - | TC-MAN-FLOW-002 |
| AC-12.5 | Admins can list/filter listings, change status, and delete listings. | TC-API-ADM-040, TC-API-ADM-041, TC-API-ADM-042, TC-API-ADM-043, TC-API-ADM-044, TC-API-ADM-045, TC-API-ADM-046, TC-API-ADM-047 | - | TC-MAN-FLOW-002 |
| AC-12.6 | Admins can list/filter needs and delete needs. | TC-API-ADM-050, TC-API-ADM-051, TC-API-ADM-052, TC-API-ADM-053 | - | TC-MAN-FLOW-002 |
| AC-12.7 | Admin routes are throttled. | TC-API-ADM-003, TC-SVC-CFG-003 | - | TC-MAN-FLOW-002 |
| AC-13.1 | Each effective admin mutation writes an audit entry (actor, action, target, IP, details). | TC-API-ADM-024, TC-API-ADM-043, TC-API-ADM-046, TC-API-ADM-052, TC-DI-CAS-005 | - | TC-MAN-DB-003, TC-MAN-FLOW-002 |
| AC-13.2 | Unchanged/no-op admin updates write no audit entry. | TC-API-ADM-031 | - | TC-MAN-FLOW-002 |
| AC-13.3 | The audit log is newest first, paginated (limit 1-100) and shows the actor name. | TC-API-ADM-060, TC-API-ADM-061, TC-API-ADM-062, TC-API-ADM-063 | - | TC-MAN-FLOW-002 |
| AC-14.1 | Cleanup deletes expired listings (and their Cloudinary assets) and expired needs and keeps current ones. | TC-SVC-CLN-001, TC-SVC-CLN-002, TC-SVC-CLN-003, TC-SVC-CLN-004, TC-SVC-CLN-006, TC-SVC-CLN-007 | - | TC-MAN-IMG-003, TC-MAN-OPS-001 |
| AC-14.2 | A Cloudinary failure during cleanup does not stop the run. | TC-SVC-CLN-005 | - | - |
| AC-15.1 | Sliding-window limiter: per-key counting, 429 with Retry-After, window expiry. | TC-SVC-RLM-001, TC-SVC-RLM-002, TC-SVC-RLM-003, TC-SVC-RLM-004, TC-SVC-RLM-005, TC-SVC-RLM-010, TC-SVC-RLM-011, TC-SVC-RLM-012, TC-SVC-RLM-020, TC-SVC-RLM-021 | test_rate_limiter_bounds_memory_under_key_rotation, test_rate_limiter_window_expiry, test_registration_rate_limit_returns_429 | TC-MAN-OPS-002 |
| AC-15.2 | Per-account limiter keys are hashed and case-insensitive. | TC-SVC-RLM-022, TC-SVC-RLM-023 | - | - |
| AC-16.1 | Only JPEG/PNG/WebP by declared type and magic bytes, within the size limit. | TC-SVC-CFG-001, TC-SVC-IMG-001, TC-SVC-IMG-002, TC-SVC-IMG-003, TC-SVC-IMG-004, TC-SVC-IMG-005, TC-SVC-IMG-006, TC-SVC-IMG-011, TC-SVC-IMG-012, TC-SVC-IMG-013, TC-SVC-IMG-014, TC-SVC-IMG-015 | - | TC-MAN-IMG-001, TC-MAN-UI-001 |
| AC-16.2 | Images are stored under a per-listing Cloudinary folder. | TC-SVC-IMG-010 | - | TC-MAN-IMG-001 |
| AC-17.1 | Security headers are set on responses (HSTS only when enabled; no-store on sensitive paths; CSP exemptions for docs). | TC-SVC-CFG-004 | test_csp_exempts_docs_paths, test_hsts_absent_when_disabled, test_hsts_present_when_enabled, test_security_headers_present, test_sensitive_endpoints_not_cached | TC-MAN-SEC-002 |
| AC-17.2 | A safe client X-Request-ID is echoed; otherwise one is generated. | - | test_request_id_is_not_echoed_when_malformed, test_request_id_is_returned | - |
| AC-17.3 | CORS allows only configured origins, never a wildcard. | TC-SVC-CFG-010, TC-SVC-CFG-011 | test_cors_allows_configured_origin, test_cors_blocks_unknown_origin_preflight, test_cors_rejects_wildcard_with_credentials | TC-MAN-SEC-001 |
| AC-17.4 | API documentation endpoints are disabled in production. | - | - | TC-MAN-SEC-003 |
| AC-18.1 | Validation failures return 422 with a readable detail (string for one error, list for several) and never echo secrets. | TC-VAL-ERR-001, TC-VAL-ERR-002, TC-VAL-ERR-003, TC-VAL-ERR-004, TC-VAL-ERR-005 | - | - |
| AC-18.2 | Unexpected server errors return a generic 500 without internal details. | - | test_errors_do_not_leak_internal_details | - |
| AC-19.1 | Uniqueness is enforced for email, phone and (listing, user) interest. | TC-API-INT-008, TC-API-REG-013, TC-DI-UNQ-001, TC-DI-UNQ-002, TC-DI-UNQ-003, TC-DI-UNQ-004, TC-DI-UNQ-005 | - | - |
| AC-19.2 | Defaults and enum values persist correctly. | TC-DI-DEF-001, TC-DI-DEF-002, TC-DI-DEF-003, TC-DI-DEF-004, TC-DI-VAL-002 | - | - |
| AC-19.3 | Deleting a parent removes dependent records; unrelated records are untouched. | TC-API-ADM-046, TC-API-LST-019, TC-API-LST-080, TC-DI-CAS-001, TC-DI-CAS-002, TC-DI-CAS-003, TC-DI-CAS-004, TC-DI-CAS-005, TC-SVC-CLN-006 | - | TC-MAN-DB-002, TC-MAN-DB-003 |
| AC-19.4 | Startup migrations build the full schema at head and are idempotent; the unpooled URL is preferred. | TC-SVC-MIG-001, TC-SVC-MIG-002, TC-SVC-MIG-003 | - | TC-MAN-DB-001 |
| AC-19.5 | Migration failure is fatal in production and tolerated elsewhere. | TC-SVC-MIG-004, TC-SVC-MIG-005, TC-SVC-MIG-006 | - | TC-MAN-DB-004 |
| AC-19.6 | Passwords are never stored or returned in plaintext. | TC-API-REG-002, TC-DI-VAL-003, TC-SVC-AUT-001 | - | - |
| AC-20.1 | Required settings are mandatory. | TC-SVC-CFG-013, TC-SVC-CFG-020 | - | - |
| AC-20.2 | Documented defaults apply when settings are absent. | TC-SVC-CFG-001, TC-SVC-CFG-002, TC-SVC-CFG-003, TC-SVC-CFG-004 | - | - |
| AC-20.3 | Comma-separated settings are parsed, trimmed and normalised. | TC-SVC-CFG-010, TC-SVC-CFG-011, TC-SVC-CFG-012 | - | - |

## 7. Service test scenarios

Files: `test_service_config.py`, `test_service_auth.py`, `test_service_rate_limit.py`, `test_service_cloudinary.py`, `test_service_cleanup_migration.py`.

### Password and token service (T04)

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-SVC-AUT-001 | positive | AC-01.4, AC-19.6 | T04 | hash is Argon2id and never equals the plaintext |
| TC-SVC-AUT-002 | business | AC-01.4 | T04 | each hash uses a fresh salt, yet both verify |
| TC-SVC-AUT-003 | positive | AC-02.1 | T04 | correct password verifies |
| TC-SVC-AUT-004 | negative | AC-02.2 | T04 | wrong password does not verify |
| TC-SVC-AUT-005 | boundary | AC-02.2 | T04 | a case change makes the password invalid |
| TC-SVC-AUT-006 | boundary | AC-01.4 | T04 | a 100-character password hashes and verifies |
| TC-SVC-AUT-007 | positive | AC-01.4 | T04 | non-ASCII passwords hash and verify |
| TC-SVC-AUT-010 | positive | AC-02.1, AC-03.1 | T04 | token round-trips to the same integer user id |
| TC-SVC-AUT-011 | positive | AC-02.1 | T04 | 'sub' claim carries the user id as a string |
| TC-SVC-AUT-012 | boundary | AC-02.1 | T04 | 'exp' is now + ACCESS_TOKEN_EXPIRE_MINUTES (within 10 s) |
| TC-SVC-AUT-013 | negative | AC-03.2 | T04 | a token whose exp is in the past is rejected |
| TC-SVC-AUT-014 | negative | AC-03.2 | T04 | a token signed with a different secret is rejected |
| TC-SVC-AUT-015 | negative | AC-03.2 | T04 | a validly signed token with no 'sub' raises ValueError |
| TC-SVC-AUT-016 | negative | AC-03.2 | T04 | a non-numeric 'sub' raises ValueError |
| TC-SVC-AUT-017 | negative | AC-03.2 | T04 | a malformed string is rejected |
| TC-SVC-AUT-018 | negative | AC-03.2 | T04 | a token signed with HS512 is rejected even with the right secret |

### Rate limiter and key helpers (T13)

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-SVC-RLM-001 | boundary | AC-15.1 | T13 | exactly max_requests are allowed; the next one is blocked |
| TC-SVC-RLM-002 | business | AC-15.1 | T13 | exhausting one key does not affect another |
| TC-SVC-RLM-003 | boundary | AC-15.1 | T13 | 59.9 s after the first request the slot is still taken |
| TC-SVC-RLM-004 | boundary | AC-15.1 | T13 | exactly one full window later the slot is free again |
| TC-SVC-RLM-005 | business | AC-15.1 | T13 | rejected attempts are not recorded, so the block ends on schedule |
| TC-SVC-RLM-010 | positive | AC-15.1 | T13 | enforce() is silent while under the limit |
| TC-SVC-RLM-011 | negative | AC-15.1 | T13 | over the limit: 429, supplied detail, Retry-After = window |
| TC-SVC-RLM-012 | business | AC-15.1 | T13 | the dependency keys by '<scope>:<ip>' |
| TC-SVC-RLM-020 | positive | AC-15.1 | T13 | key format is '<scope>:<client ip>' |
| TC-SVC-RLM-021 | boundary | AC-15.1 | T13 | a request with no client address maps to 'unknown' |
| TC-SVC-RLM-022 | business | AC-15.2 | T13 | the account key hides the email and ignores case |
| TC-SVC-RLM-023 | negative | AC-15.2 | T13 | different emails never share a key |

### Image validation and Cloudinary wrapper (T09)

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-SVC-IMG-001 | positive | AC-16.1 | T09 | JPEG, PNG and WebP signatures are accepted *(parametrized)* |
| TC-SVC-IMG-002 | negative | AC-16.1 | T09 | a GIF signature is rejected |
| TC-SVC-IMG-003 | negative | AC-16.1 | T09 | arbitrary text renamed to .png is rejected |
| TC-SVC-IMG-004 | boundary | AC-16.1 | T09 | 11 bytes is below the 12-byte minimum |
| TC-SVC-IMG-005 | boundary | AC-16.1 | T09 | exactly 12 bytes with a valid signature passes |
| TC-SVC-IMG-006 | negative | AC-16.1 | T09 | a RIFF container that is not WebP (e.g. WAV) is rejected |
| TC-SVC-IMG-010 | positive | AC-16.2 | T09 | valid PNG uploads into infyexchange/listings/<id> and returns id + url |
| TC-SVC-IMG-011 | positive | AC-16.1 | T09 | JPEG and WebP uploads are accepted *(parametrized)* |
| TC-SVC-IMG-012 | negative | AC-16.1 | T09 | image/gif is refused and nothing is sent to Cloudinary |
| TC-SVC-IMG-013 | negative | AC-16.1 | T09 | image/png header with non-image bytes is rejected |
| TC-SVC-IMG-014 | boundary | AC-16.1 | T09 | a file of exactly MAX_IMAGE_SIZE_MB passes |
| TC-SVC-IMG-015 | boundary | AC-16.1 | T09 | one byte over MAX_IMAGE_SIZE_MB is rejected |
| TC-SVC-IMG-020 | positive | AC-07.4 | T09 | delete_image destroys the asset by public id and invalidates the CDN |

### Expiry cleanup (T15)

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-SVC-CLN-001 | positive | AC-14.1 | T15 | an expired listing, its image rows and its Cloudinary assets are deleted |
| TC-SVC-CLN-002 | boundary | AC-14.1 | T15 | a listing expiring one hour from now is untouched |
| TC-SVC-CLN-003 | positive | AC-14.1 | T15 | expired needs are deleted, current needs are kept |
| TC-SVC-CLN-004 | business | AC-14.1 | T15 | an expired SOLD listing and a CLOSED need are removed too |
| TC-SVC-CLN-005 | negative | AC-14.2 | T15 | a failing asset deletion is logged and the rows are still removed |
| TC-SVC-CLN-006 | business | AC-14.1, AC-19.3 | T15 | interests on an expired listing disappear with it |
| TC-SVC-CLN-007 | boundary | AC-14.1 | T15 | running on an empty/current database changes nothing |

### Startup migrations (T03)

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-SVC-MIG-001 | positive | AC-19.4 | T03 | apply_migrations on an empty DB creates all six tables at the head revision |
| TC-SVC-MIG-002 | boundary | AC-19.4 | T03 | running migrations twice succeeds and leaves the same revision |
| TC-SVC-MIG-003 | business | AC-19.4 | T03 | migrations use DATABASE_URL_UNPOOLED when it is set |
| TC-SVC-MIG-004 | negative | AC-19.5 | T03 | in production a failed migration re-raises so the instance does not start |
| TC-SVC-MIG-005 | business | AC-19.5 | T03 | in development a failed migration is logged and startup continues |
| TC-SVC-MIG-006 | boundary | AC-19.5 | T03 | ENVIRONMENT='Production' is still treated as production |

### Settings (T01)

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-SVC-CFG-001 | positive | AC-20.2, AC-04.1, AC-04.4, AC-04.5, AC-16.1 | T01 | 30-day expiry, 5 images of 5 MB, 60 s duplicate window |
| TC-SVC-CFG-002 | positive | AC-20.2, AC-02.1 | T01 | HS256 tokens valid for 10080 minutes (7 days) |
| TC-SVC-CFG-003 | positive | AC-20.2, AC-02.4, AC-05.5, AC-10.3, AC-12.7 | T01 | 60 s window; login 10, register 5, create 10, read 120, contact 20, admin 60 |
| TC-SVC-CFG-004 | business | AC-20.2, AC-17.1 | T01 | HSTS must be explicitly enabled |
| TC-SVC-CFG-010 | boundary | AC-20.3, AC-17.3 | T01 | comma list is trimmed and empty entries are dropped |
| TC-SVC-CFG-011 | boundary | AC-20.3, AC-17.3 | T01 | an empty CORS_ORIGINS allows no origin |
| TC-SVC-CFG-012 | boundary | AC-20.3, AC-01.2 | T01 | domains are normalised to lowercase without whitespace |
| TC-SVC-CFG-013 | business | AC-20.1 | T01 | stray env vars do not break startup |
| TC-SVC-CFG-020 | negative | AC-20.1 | T01 | omitting any required setting stops the app from starting *(parametrized)* |

## 8. API test scenarios

Files: `test_api_auth_flows.py`, `test_api_users.py`, `test_api_listings.py`, `test_api_needs.py`, `test_api_interests.py`, `test_api_admin.py`. Status-code expectations follow the endpoint table in Appendix A.3: success codes per endpoint; `401/403` unauthenticated (the exact code depends on the FastAPI version, so tests accept either); `403` forbidden; `404` missing; `409` conflict; `422` validation; `429` throttled.

### POST /api/auth/register

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-REG-001 | positive | AC-01.1, AC-01.6 | T05 | 201 with profile; role/date echoed; non-admin, active; no password data |
| TC-API-REG-002 | positive | AC-01.4, AC-19.6 | T05 | persisted password is an Argon2id hash, not the submitted text |
| TC-API-REG-003 | business | AC-01.2 | T05 | mixed-case email (and domain) is normalised to lowercase |
| TC-API-REG-004 | business | AC-01.5 | T05 | surrounding whitespace is stripped from name and phone before saving |
| TC-API-REG-005 | negative | AC-01.6 | T05 | is_admin / is_active in the request body are ignored |
| TC-API-REG-006 | business | AC-01.1, AC-02.1 | T05 | the new credentials work at /login straight away |
| TC-API-REG-007 | negative | AC-01.2 | T05 | other domains, look-alikes and sub-domains of gmail.com get 400 *(parametrized)* |
| TC-API-REG-008 | business | AC-01.2 | T05 | with several configured domains each is accepted and the error lists them |
| TC-API-REG-009 | boundary | AC-01.2 | T05 | an empty ALLOWED_EMAIL_DOMAINS behaves as gmail.com only |
| TC-API-REG-010 | negative | AC-01.3 | T05 | a second registration with the same email gets 409 |
| TC-API-REG-011 | boundary | AC-01.3 | T05 | DUP@gmail.com collides with dup@gmail.com |
| TC-API-REG-012 | negative | AC-01.3 | T05 | a different email with an already-used phone gets 409 |
| TC-API-REG-013 | business | AC-01.3, AC-19.1 | T05 | a rejected registration leaves no row behind |

### POST /api/auth/login

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-LOG-001 | positive | AC-02.1 | T05 | 200 with a bearer token whose subject is the user's id |
| TC-API-LOG-002 | positive | AC-02.1, AC-03.1 | T05 | the issued token is accepted by /api/auth/me |
| TC-API-LOG-003 | negative | AC-02.2 | T05 | unknown account and wrong password give the same status and message |
| TC-API-LOG-004 | boundary | AC-02.3 | T05 | logging in with an upper-case email succeeds |
| TC-API-LOG-005 | boundary | AC-02.4 | T05 | the 10th login in a window passes and the 11th is throttled |
| TC-API-LOG-006 | negative | AC-02.4 | T05 | once the per-IP counter is cleared the per-account limit still blocks the same email |
| TC-API-LOG-007 | business | AC-02.4 | T05 | exhausting one account's limit does not lock out a different account |
| TC-API-LOG-008 | boundary | AC-02.2 | T05 | a 101-character password is a 422, not a hash comparison |
| TC-API-LOG-009 | negative | AC-02.2 | T05 | missing or malformed fields are rejected before any lookup *(parametrized)* |

### GET /api/auth/me, /api/users/me

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-IDN-001 | positive | AC-03.1 | T06, T07 | /api/auth/me and /api/users/me return the caller's profile |
| TC-API-IDN-002 | negative | AC-03.2 | T06 | an expired token yields 401 'Invalid or expired token' |
| TC-API-IDN-003 | negative | AC-03.2 | T06 | a valid token whose user no longer exists yields 401 'User not found' |
| TC-API-IDN-004 | negative | AC-03.2 | T06 | tokens with a bad subject or bad signature never authenticate *(parametrized)* |
| TC-API-IDN-005 | negative | AC-03.2 | T06 | 'Basic' credentials are not accepted as a token |
| TC-API-IDN-006 | negative | AC-03.3 | T06 | a deactivated account is refused with 403 and an explanatory message |

### GET /api/users/me/summary

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-USR-001 | boundary | AC-11.1 | T07 | a user with no activity gets five zero counters |
| TC-API-USR-002 | positive | AC-11.1 | T07 | counters match 2 listings, 1 need, 1 sent interest, 2 received (1 pending) |
| TC-API-USR-003 | business | AC-11.1 | T07 | counters are scoped to the caller |
| TC-API-USR-004 | negative | AC-11.1 | T07 | anonymous callers get 401/403 |

### /api/listings*

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-LST-001 | positive | AC-04.1 | T08 | 201; caller is owner; status ACTIVE; fields echoed |
| TC-API-LST-002 | business | AC-04.1 | T08 | expires_at is created_at + LISTING_EXPIRY_DAYS (30) |
| TC-API-LST-003 | business | AC-04.3 | T08 | surrounding whitespace is stripped before saving |
| TC-API-LST-004 | negative | AC-04.6 | T08 | no token: 401/403 and nothing is created |
| TC-API-LST-005 | negative | AC-04.2 | T08 | SELL and RENT without a price > 0 get 400 *(parametrized)* |
| TC-API-LST-006 | boundary | AC-04.2 | T08 | price 1 is accepted for SELL |
| TC-API-LST-007 | business | AC-04.2 | T08 | LEND/GIVEAWAY ignore a submitted price and unit *(parametrized)* |
| TC-API-LST-008 | business | AC-04.2 | T08 | RENT without price_unit is stored per 'day' |
| TC-API-LST-009 | positive | AC-04.2 | T08 | RENT with price_unit 'week' keeps it |
| TC-API-LST-010 | boundary | AC-04.3 | T08 | title 2-150, location 2-100, description 2-2000 characters *(parametrized)* |
| TC-API-LST-011 | negative | AC-04.3 | T08 | out-of-range, unknown-enum and missing required fields are rejected *(parametrized)* |
| TC-API-LST-012 | business | AC-04.4 | T08 | the same form within the window returns the first listing; only one row exists |
| TC-API-LST-013 | business | AC-04.4 | T08 | a different description creates a second listing |
| TC-API-LST-014 | business | AC-04.4 | T08 | duplicate detection is per owner |
| TC-API-LST-015 | boundary | AC-04.4 | T08 | with DUPLICATE_SUBMISSION_WINDOW_SECONDS=0 identical submissions both create rows |
| TC-API-LST-016 | positive | AC-04.5 | T08, T09 | three uploaded images are stored and the first upload becomes the card image |
| TC-API-LST-017 | boundary | AC-04.5 | T08 | exactly MAX_IMAGES_PER_LISTING (5) is accepted |
| TC-API-LST-018 | boundary | AC-04.5 | T08 | a sixth image gives 400, creates no listing and uploads nothing |
| TC-API-LST-019 | negative | AC-04.5, AC-19.3 | T08, T09 | if image 2 fails: 400, no listing row, image 1 is deleted from Cloudinary |
| TC-API-LST-020 | boundary | AC-04.6 | T08, T13 | with the create limit at 2, the third creation is 429 with Retry-After |
| TC-API-LST-030 | business | AC-05.1 | T08 | anonymous callers see ACTIVE, unexpired listings only |
| TC-API-LST-031 | boundary | AC-05.1 | T08 | no listings: 200 with [] |
| TC-API-LST-032 | positive | AC-05.2 | T08 | search is a case-insensitive title substring |
| TC-API-LST-033 | positive | AC-05.2 | T08 | enum filters match exactly; location is a case-insensitive substring |
| TC-API-LST-034 | boundary | AC-05.2 | T08 | min_price and max_price include listings priced exactly at the bound |
| TC-API-LST-035 | business | AC-05.3 | T08 | listings are ordered by created_at descending |
| TC-API-LST-036 | boundary | AC-05.3 | T08 | limit caps page size; skip offsets; skipping past the end gives [] |
| TC-API-LST-037 | boundary | AC-05.3 | T08 | with 21 listings and no limit, 20 are returned |
| TC-API-LST-038 | boundary | AC-05.3 | T08 | limit 1-100, skip >= 0, prices >= 0, enum values validated *(parametrized)* |
| TC-API-LST-039 | business | AC-05.4, AC-10.4 | T08 | cards carry owner name/role and image but never email, phone or hashes |
| TC-API-LST-040 | boundary | AC-05.5 | T08, T13 | with the read limit at 3 the fourth browse request is 429 |
| TC-API-LST-050 | positive | AC-06.1 | T08 | public detail returns the listing with all its images |
| TC-API-LST-051 | negative | AC-06.1 | T08 | unknown id gives 404 'Listing not found' |
| TC-API-LST-052 | boundary | AC-06.1 | T08 | an ACTIVE listing past expires_at gives 404 'Listing has expired' |
| TC-API-LST-053 | negative | AC-06.1 | T08 | a non-integer id is a validation error |
| TC-API-LST-060 | business | AC-06.2 | T08 | /me includes the caller's SOLD and expired listings and excludes other users' |
| TC-API-LST-061 | negative | AC-06.2 | T08 | /me without a token is 401/403 |
| TC-API-LST-062 | boundary | AC-06.2 | T08 | limit and skip are honoured and limit 101 is rejected |
| TC-API-LST-070 | positive | AC-07.1 | T08 | PUT with {title, price} updates those and leaves the rest unchanged |
| TC-API-LST-071 | boundary | AC-07.1 | T08 | PUT {} is accepted and leaves the listing as it was |
| TC-API-LST-072 | business | AC-07.1, AC-05.1 | T08 | after the owner sets status SOLD the listing no longer appears in browse |
| TC-API-LST-073 | negative | AC-07.2 | T08 | PUT on a missing id is 404; PUT without a token is 401/403 |
| TC-API-LST-074 | boundary | AC-07.3 | T08 | title 2-150, price >= 0, enum values validated on update *(parametrized)* |
| TC-API-LST-080 | positive | AC-07.4, AC-19.3 | T08, T09 | delete removes the row, its image rows, interests and the Cloudinary assets |
| TC-API-LST-081 | business | AC-07.4 | T08 | after delete, GET by id is 404 |
| TC-API-LST-082 | negative | AC-07.2 | T08 | DELETE on a missing id is 404; without a token is 401/403 |
| TC-API-LST-083 | negative | AC-07.2 | T08 | a stranger gets 403 and no images are removed |

### /api/needs*

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-NED-001 | positive | AC-08.1 | T11 | 201 with caller as owner, status ACTIVE and echoed fields |
| TC-API-NED-002 | business | AC-08.1 | T11 | expires_at is created_at + LISTING_EXPIRY_DAYS (30) |
| TC-API-NED-003 | business | AC-08.2 | T11 | whitespace around title, location and description is stripped |
| TC-API-NED-004 | negative | AC-08.1 | T11 | no token: 401/403 |
| TC-API-NED-005 | boundary | AC-08.2 | T11 | title 2-150, location 2-100, description 2-2000, duration <= 100, budget >= 0 *(parametrized)* |
| TC-API-NED-006 | negative | AC-08.2 | T11 | unknown enum values and non-numeric budget are rejected *(parametrized)* |
| TC-API-NED-007 | negative | AC-08.2 | T11 | an empty body is rejected |
| TC-API-NED-008 | positive | AC-08.2 | T11 | omitting budget and duration defaults them to 0 and null |
| TC-API-NED-009 | business | AC-08.3 | T11 | the same need within the window returns the first one; one row exists |
| TC-API-NED-010 | business | AC-08.3 | T11 | a different description is not a duplicate |
| TC-API-NED-011 | boundary | AC-08.7 | T11, T13 | with the create limit at 2 the third need is 429 |
| TC-API-NED-020 | business | AC-08.4 | T11 | anonymous callers see ACTIVE, unexpired needs with the poster's name |
| TC-API-NED-021 | business | AC-08.4, AC-10.4 | T11 | need payloads contain no email, phone or hash |
| TC-API-NED-022 | positive | AC-08.4 | T11 | search (title substring, any case), category, need_type and location filter results |
| TC-API-NED-023 | boundary | AC-08.4 | T11 | ordered newest first; limit/skip page the results |
| TC-API-NED-024 | boundary | AC-08.4 | T11 | limit 1-100, skip >= 0, enum filters validated *(parametrized)* |
| TC-API-NED-025 | boundary | AC-08.7 | T11, T13 | with the read limit at 2 the third browse is 429 |
| TC-API-NED-030 | business | AC-08.5 | T11 | /me lists the caller's needs of any status or age and none of others' |
| TC-API-NED-031 | negative | AC-08.5 | T11 | /me without a token is 401/403 |
| TC-API-NED-032 | positive | AC-08.5 | T11 | GET by id works anonymously |
| TC-API-NED-033 | negative | AC-08.5 | T11 | unknown id gives 404 'Need not found' |
| TC-API-NED-034 | boundary | AC-08.5 | T11 | an ACTIVE need past expires_at gives 404 'Need has expired' |
| TC-API-NED-040 | positive | AC-08.6 | T11 | the owner deletes their need; it is gone afterwards |
| TC-API-NED-041 | negative | AC-08.6 | T11 | a different user gets 403 and the need remains |
| TC-API-NED-042 | negative | AC-08.6 | T11 | DELETE of a missing id is 404; without a token it is 401/403 |

### /api/interests*

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-INT-001 | positive | AC-09.1 | T10 | 201, status PENDING, message and ids stored |
| TC-API-INT-002 | boundary | AC-09.1 | T10 | an empty JSON body creates an interest with a null message |
| TC-API-INT-003 | boundary | AC-09.1 | T10 | a 500-character message is accepted, 501 is rejected *(parametrized)* |
| TC-API-INT-004 | negative | AC-09.2 | T10 | no token: 401/403 |
| TC-API-INT-005 | negative | AC-09.2 | T10 | interest in a missing listing gives 404 |
| TC-API-INT-006 | negative | AC-09.2 | T10 | interest in a non-ACTIVE listing gives 400 *(parametrized)* |
| TC-API-INT-007 | boundary | AC-09.2 | T10 | an ACTIVE listing past expires_at gives 400 'expired' |
| TC-API-INT-008 | negative | AC-09.2, AC-19.1 | T10 | repeating interest gives 409 and keeps a single row |
| TC-API-INT-009 | positive | AC-09.2 | T10 | two users can both express interest in the same listing |
| TC-API-INT-010 | business | AC-09.2 | T10 | the uniqueness rule is per (listing, user), not per user |
| TC-API-INT-011 | boundary | AC-09.1 | T10, T13 | with the create limit at 1 the second interest is 429 |
| TC-API-INT-020 | positive | AC-09.3 | T10 | owner sees buyer name/role, listing title and image; no contact details |
| TC-API-INT-021 | business | AC-09.3 | T10 | a user only sees requests for their own listings |
| TC-API-INT-022 | positive | AC-09.3 | T10 | the buyer sees their own interest (name = themselves); others do not |
| TC-API-INT-023 | negative | AC-09.3 | T10 | /received and /sent reject anonymous callers |
| TC-API-INT-024 | boundary | AC-09.3 | T10 | limit/skip page the lists; limit 101 and skip -1 are rejected |
| TC-API-INT-025 | business | AC-09.3 | T10 | requests are ordered by creation time, newest first |
| TC-API-INT-030 | positive | AC-09.4 | T10 | the listing owner moves PENDING to ACCEPTED or REJECTED *(parametrized)* |
| TC-API-INT-031 | negative | AC-09.4 | T10 | the interested user and strangers get 403; status stays PENDING *(parametrized)* |
| TC-API-INT-032 | negative | AC-09.4 | T10 | a missing interest id gives 404 *(parametrized)* |
| TC-API-INT-033 | negative | AC-09.4 | T10 | accepted/rejected interests are final: any further accept/reject is 400 *(parametrized)* |
| TC-API-INT-034 | negative | AC-09.4 | T10 | anonymous accept/reject is 401/403 |
| TC-API-INT-035 | business | AC-09.5 | T10 | accepting one interest leaves the listing ACTIVE and other pending requests untouched |
| TC-API-INT-036 | business | AC-09.5 | T10 | multiple buyers can be accepted for the same listing |
| TC-API-INT-040 | positive | AC-10.1 | T10 | each side receives only {name, email, phone} of the other party |
| TC-API-INT-041 | negative | AC-10.2 | T10 | a REJECTED interest gives 403 to both parties |
| TC-API-INT-042 | negative | AC-10.2 | T10 | a missing interest id gives 404 |
| TC-API-INT-043 | negative | AC-10.2 | T10 | anonymous reveal is 401/403 |
| TC-API-INT-044 | boundary | AC-10.3 | T10, T13 | with the contact limit at 1 the second reveal is 429 with Retry-After |
| TC-API-INT-045 | business | AC-09.1, AC-09.4, AC-10.1 | T10 | send -> blocked -> accept -> contact available, end to end |

### /api/admin/*

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-API-ADM-001 | negative | AC-12.1 | T12 | every admin route returns 403 for a regular member *(parametrized)* |
| TC-API-ADM-002 | negative | AC-12.1 | T12 | every admin route rejects callers without a token *(parametrized)* |
| TC-API-ADM-003 | boundary | AC-12.7 | T12, T13 | with the admin limit at 2 the third request is 429 |
| TC-API-ADM-004 | negative | AC-12.1, AC-03.3 | T12, T06 | an admin whose account is deactivated gets 403 |
| TC-API-ADM-010 | positive | AC-12.2 | T12 | total/active counts for users, listings, needs and interests |
| TC-API-ADM-011 | boundary | AC-12.2 | T12 | with no content, everything but the admin user is zero |
| TC-API-ADM-020 | positive | AC-12.3 | T12 | {total, items[]} with profile fields and without password data |
| TC-API-ADM-021 | positive | AC-12.3 | T12 | search finds substrings of email or name; no match gives total 0 |
| TC-API-ADM-022 | boundary | AC-12.3 | T12 | limit reduces items but total still counts every match |
| TC-API-ADM-023 | boundary | AC-12.3 | T12 | admin user lists accept limit 1-200 *(parametrized)* |
| TC-API-ADM-024 | positive | AC-12.4, AC-13.1 | T12 | is_active=false persists and an UPDATE_USER audit row records from/to |
| TC-API-ADM-025 | business | AC-12.4, AC-03.3 | T12, T06 | the deactivated member's existing token is refused on the next call |
| TC-API-ADM-026 | business | AC-12.4 | T12 | setting is_active back to true lets the member in again |
| TC-API-ADM-027 | positive | AC-12.4 | T12 | promoting a member lets them reach admin routes |
| TC-API-ADM-028 | positive | AC-12.4 | T12 | demoting a different admin succeeds |
| TC-API-ADM-029 | negative | AC-12.4 | T12 | self-demotion gives 400, keeps admin rights and writes no audit row |
| TC-API-ADM-030 | negative | AC-12.4 | T12 | updating a missing user gives 404 |
| TC-API-ADM-031 | boundary | AC-13.2 | T12 | empty or unchanged payloads succeed without creating an audit row *(parametrized)* |
| TC-API-ADM-032 | negative | AC-12.4 | T12 | a non-boolean value is rejected |
| TC-API-ADM-040 | positive | AC-12.5 | T12 | admin list includes owner name/email and image_count |
| TC-API-ADM-041 | positive | AC-12.5 | T12 | status_filter and title search narrow the list; all statuses are visible by default |
| TC-API-ADM-042 | boundary | AC-12.5 | T12 | invalid status and limits outside 1-200 are rejected *(parametrized)* |
| TC-API-ADM-043 | positive | AC-12.5, AC-13.1 | T12 | status=UNAVAILABLE persists, removes the listing from public browse, and audits old/new |
| TC-API-ADM-044 | negative | AC-12.5 | T12 | missing or unknown status query value is 422 and nothing changes *(parametrized)* |
| TC-API-ADM-045 | negative | AC-12.5 | T12 | missing listing gives 404 |
| TC-API-ADM-046 | positive | AC-12.5, AC-13.1, AC-19.3 | T12 | deleting a listing removes it and its interests; DELETE_LISTING audit stores the title |
| TC-API-ADM-047 | negative | AC-12.5 | T12 | missing listing gives 404 |
| TC-API-ADM-050 | positive | AC-12.6 | T12 | admin sees every need with poster email; status_filter and search narrow it |
| TC-API-ADM-051 | boundary | AC-12.6 | T12 | invalid status and limit > 200 are rejected *(parametrized)* |
| TC-API-ADM-052 | positive | AC-12.6, AC-13.1 | T12 | deleting a need removes it and writes DELETE_NEED with its title |
| TC-API-ADM-053 | negative | AC-12.6 | T12 | missing need gives 404 |
| TC-API-ADM-060 | business | AC-13.3 | T12 | entries are returned newest first and show the actor's name |
| TC-API-ADM-061 | boundary | AC-13.3 | T12 | with no admin actions the log is empty |
| TC-API-ADM-062 | boundary | AC-13.3 | T12 | audit log limit accepts 1-100 only *(parametrized)* |
| TC-API-ADM-063 | boundary | AC-13.3 | T12 | limit/skip page the log while total counts all entries |

## 9. Validation test scenarios

File: `test_validation_schemas.py` (schema-level boundaries) plus input-boundary cases in the API tests (`TC-API-LST-010/011/038/074`, `TC-API-NED-005/006/024`, `TC-API-INT-003`, `TC-API-ADM-023/042/051/062`).

### RegisterRequest

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-VAL-REG-001 | boundary | AC-01.5 | T05 | name must be 2-100 characters *(parametrized)* |
| TC-VAL-REG-002 | boundary | AC-01.5 | T05 | phone must be 10-15 characters *(parametrized)* |
| TC-VAL-REG-003 | boundary | AC-01.4 | T05 | password 8-100 characters with at least one letter and one digit *(parametrized)* |
| TC-VAL-REG-004 | negative | AC-01.2 | T05 | strings that are not email addresses fail validation *(parametrized)* |
| TC-VAL-REG-005 | positive | AC-01.5 | T05 | all four defined roles are valid *(parametrized)* |
| TC-VAL-REG-006 | negative | AC-01.5 | T05 | undefined roles (including wrong case) are rejected *(parametrized)* |
| TC-VAL-REG-007 | negative | AC-01.5 | T05 | impossible or non-ISO dates are rejected *(parametrized)* |
| TC-VAL-REG-008 | negative | AC-01.5 | T05 | omitting any single field fails validation *(parametrized)* |

### LoginRequest

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-VAL-LOG-001 | boundary | AC-02.2 | T05 | 100-character password is accepted by the schema |
| TC-VAL-LOG-002 | boundary | AC-02.2 | T05 | 101 characters fails |
| TC-VAL-LOG-003 | business | AC-02.2 | T05 | a short, letters-only password is not a schema error at login (it simply fails authentication) |

### NeedCreate

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-VAL-NED-001 | boundary | AC-08.2 | T11 | title 2-150, location 2-100, description 2-2000, duration <= 100 *(parametrized)* |
| TC-VAL-NED-002 | boundary | AC-08.2 | T11 | budget >= 0 *(parametrized)* |
| TC-VAL-NED-003 | positive | AC-08.2 | T11 | budget defaults to 0 and duration to None |
| TC-VAL-NED-004 | negative | AC-08.2 | T11 | undefined or wrongly-cased enum values are rejected *(parametrized)* |

### ListingUpdate

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-VAL-LST-001 | boundary | AC-07.1 | T08 | an empty update is valid and carries no fields |
| TC-VAL-LST-002 | boundary | AC-07.3 | T08 | title 2-150 characters when supplied *(parametrized)* |
| TC-VAL-LST-003 | boundary | AC-07.3 | T08 | price >= 0 when supplied *(parametrized)* |
| TC-VAL-LST-004 | negative | AC-07.3 | T08 | unknown enum values and non-numeric price fail *(parametrized)* |
| TC-VAL-LST-005 | business | AC-07.1 | T08 | exclude_unset yields just the fields the client sent |

### InterestCreate

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-VAL-INT-001 | boundary | AC-09.1 | T10 | message of 0-500 characters is accepted, 501 is not *(parametrized)* |
| TC-VAL-INT-002 | positive | AC-09.1 | T10 | omitting the message is valid |

### 422 error contract

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-VAL-ERR-001 | positive | AC-18.1 | T16 | one invalid field gives 422 with detail as a single 'field: message' string |
| TC-VAL-ERR-002 | positive | AC-18.1 | T16 | several invalid fields give 422 with detail as a list of messages |
| TC-VAL-ERR-003 | business | AC-18.1 | T16 | validation messages do not repeat the password the client sent |
| TC-VAL-ERR-004 | positive | AC-18.1 | T16 | an out-of-range query parameter is a 422 whose detail names it |
| TC-VAL-ERR-005 | negative | AC-18.1 | T16 | invalid JSON gets a client error, never a server error |

## 10. Data integrity scenarios

File: `test_data_integrity.py` (plus `TC-SVC-MIG-001/002` for the schema built by migrations).

### Uniqueness constraints

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-DI-UNQ-001 | negative | AC-19.1 | T02 | two users cannot share an email at the storage level |
| TC-DI-UNQ-002 | negative | AC-19.1 | T02 | two users cannot share a phone number at the storage level |
| TC-DI-UNQ-003 | negative | AC-19.1 | T02, T10 | the (listing, user) unique constraint blocks a second interest row |
| TC-DI-UNQ-004 | boundary | AC-19.1 | T02 | the constraint is composite: other listings are unaffected |
| TC-DI-UNQ-005 | business | AC-01.3, AC-19.1 | T05 | repeated API registration with the same email yields exactly one stored user |

### Defaults and consistency

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-DI-DEF-001 | positive | AC-01.6, AC-19.2 | T02 | a user created without flags is non-admin, active, with a creation time |
| TC-DI-DEF-002 | positive | AC-09.1, AC-19.2 | T02 | an Interest saved without a status is PENDING |
| TC-DI-DEF-003 | positive | AC-19.2 | T02 | ORM defaults: status ACTIVE and price/budget 0 when unspecified |
| TC-DI-DEF-004 | business | AC-04.1, AC-19.2 | T08 | persisted expires_at is strictly later than created_at for API-created listings |

### Cascade behaviour

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-DI-CAS-001 | positive | AC-19.3 | T02 | ORM delete of a listing cascades to its images and interests |
| TC-DI-CAS-002 | positive | AC-19.3 | T02 | deleting a user removes everything they own, including interests others made on their listings |
| TC-DI-CAS-003 | business | AC-19.3 | T02 | another user's listings and needs survive |
| TC-DI-CAS-004 | boundary | AC-19.3 | T02 | needs and listings are independent aggregates |
| TC-DI-CAS-005 | business | AC-13.1, AC-19.3 | T12 | removing a listing through the admin API keeps the audit entry that records it |

### Persisted values

| ID | Kind | Acceptance criteria | Tasks | Scenario |
| --- | --- | --- | --- | --- |
| TC-DI-VAL-001 | positive | AC-04.5, AC-07.4 | T02 | the Cloudinary public id (needed for deletion) and url are both stored |
| TC-DI-VAL-002 | positive | AC-19.2 | T02 | status/type enums are stored and read back as enum members |
| TC-DI-VAL-003 | business | AC-01.4, AC-19.6 | T05 | no column of the stored user row contains the submitted password |

## 11. Manual verification scenarios

Run in staging with synthetic accounts. Never run destructive checks against production.

| ID | Acceptance criteria | Tasks | Steps | Expected result |
| --- | --- | --- | --- | --- |
| TC-MAN-DB-001 | AC-19.4 | T03 | Run `alembic upgrade head`, `downgrade base`, `upgrade head` against a Neon staging branch using the direct URL. | All steps succeed; the eight PostgreSQL enum types are created on upgrade and dropped on downgrade; the second upgrade succeeds. |
| TC-MAN-DB-002 | AC-19.3, AC-04.5 | T02, T08 | On PostgreSQL: delete a listing that has images and interests via SQL `DELETE FROM listings`; separately force an image-upload failure through the API. | Child rows in `listing_images` and `interests` disappear (ON DELETE CASCADE); after the failed upload no `listing_images` row remains for the removed listing. |
| TC-MAN-DB-003 | AC-13.1, AC-19.3 | T02, T12 | On PostgreSQL: delete a user that is the actor of audit rows. | The audit rows remain and `actor_id` becomes NULL (ON DELETE SET NULL); the log endpoint shows actor_name 'System'. |
| TC-MAN-DB-004 | AC-19.5 | T03 | Start two API instances simultaneously against an empty staging database. | Migrations run once (advisory lock `74193820416`); both instances become healthy; `alembic_version` has one row. |
| TC-MAN-IMG-001 | AC-16.1, AC-04.5, AC-16.2 | T08, T09 | In staging, post a listing with 5 real images (JPEG, PNG, WebP; one near 5 MB). Then try a 6th image, a 5.1 MB file, a GIF, and a text file renamed `.png`. | The five valid images appear on the listing and in Cloudinary under `infyexchange/listings/<id>`; every invalid attempt is rejected with a clear message and creates no listing. |
| TC-MAN-IMG-002 | AC-07.4 | T08, T09 | Delete a listing with images as its owner; inspect the Cloudinary folder. | The assets are removed from Cloudinary. |
| TC-MAN-IMG-003 | AC-14.1 | T15 | Create a listing with an image, move its `expires_at` into the past in staging, run `python -m app.run_cleanup`. | The listing, image rows and Cloudinary asset are removed; unexpired data is untouched. |
| TC-MAN-FLOW-001 | AC-01.1, AC-04.1, AC-09.1, AC-09.4, AC-10.1 | T05, T08, T10 | From the deployed Pages origin with two synthetic accounts: register, log in, post a listing with a photo, express interest from the second account, accept as the owner, reveal contact on both sides. | Each step succeeds; contact details appear only after acceptance and only for the two participants. |
| TC-MAN-FLOW-002 | AC-12.1..AC-13.3 | T12 | As an admin in the console: deactivate a user, change a listing's status, delete a listing and a need, open the audit tab. | Each action takes effect; the deactivated user is signed out on their next request; four audit entries appear newest first. |
| TC-MAN-FLOW-003 | AC-03.2 | T06 | Sign in, wait for (or force) token expiry, perform an action. | The SPA clears the session and shows the login page; no stale data is shown. |
| TC-MAN-SEC-001 | AC-17.3 | T14 | From the browser console on the Pages origin and on an unrelated origin, call the deployed API. | Only the Pages origin receives `access-control-allow-origin`. |
| TC-MAN-SEC-002 | AC-17.1 | T14 | `curl -i` a deployed API endpoint and inspect headers. | nosniff, frame denial, referrer/permissions policy, API CSP and `X-Request-ID` present; `Strict-Transport-Security` present when `HSTS_ENABLED=true` (see Open Question 12). |
| TC-MAN-SEC-003 | AC-17.4 | T14 | Request `/docs`, `/redoc`, `/openapi.json` on the production API. | All return 404. |
| TC-MAN-OPS-001 | AC-14.1 | T15 | After scheduling the cleanup job, observe Cloud Logging after its first run. | Log line 'Cleanup deleted N listing(s) and M need(s).' appears on schedule. |
| TC-MAN-OPS-002 | AC-15.1, AC-02.4 | T13 | Against a staging service with 2+ instances, send login attempts above the per-IP limit. | Record whether the limit is enforced per instance (expected today); decision input for Open Question 11. |
| TC-MAN-UI-001 | AC-04.3, AC-16.1 | T08 | In the posting form, enter boundary values (title 1/2/150/151 characters, 5 vs 6 images, 5 MB vs larger). | Client-side messages match the server limits and the server rejects anything the client lets through. |

## 12. Test data requirements

| Data | Used by | How it is produced |
| --- | --- | --- |
| Members: owner, buyer, stranger | API, DI | `make_user` (unique `user-<hex>@gmail.com`, unique 10-digit phone, role `SE`, password `Passw0rd1`) |
| Admin and inactive users | API (admin, identity) | `make_user(is_admin=True)` / `make_user(is_active=False)` |
| Registration payloads | auth, validation | `register_payload(email)` with per-test overrides (boundary lengths 1/2/10/15/16/100/101) |
| Listings in every status (ACTIVE, SOLD, RENTED, UNAVAILABLE), expired (`expires_at` in the past) and unexpired | browse, detail, interest, cleanup, admin | `add_listing(**overrides)` |
| Listing form data (valid and invalid) | create listing | `listing_form(**overrides)` (`None` removes a field) |
| Images | upload, cascade, cleanup | 1x1-style byte strings `PNG_BYTES`, `JPEG_BYTES`, `WEBP_BYTES`; `add_image` rows with chosen public ids |
| Needs in every status, expired/unexpired | browse, cleanup, admin | `add_need`, `need_payload` |
| Interests in every status | interests, contact, summary | `add_interest` |
| Crafted JWTs (expired, wrong secret, wrong algorithm, missing/non-numeric `sub`) | identity, token service | `jwt.encode` with test secret |
| Boundary strings | validation | `"x" * n` for n at limit-1, limit, limit+1 |
| Time control | limiter, expiry | fake clock for `rate_limit.time`; explicit `created_at`/`expires_at` offsets of seconds/minutes/days |
| Temp databases | migration tests | `tmp_path / "*.db"` (SQLite) so the shared test DB is untouched |
| Settings overrides | domains, window, limits, environment | `monkeypatch.setattr(settings, ...)` and `Settings(_env_file=None, ...)` |
| Cloudinary stand-in | listings, cleanup | `FakeCloudinary` (records uploads/deletions; can fail the Nth upload) |

No production data, real credentials or network access is needed by the automated suite.

## 13. Out of Scope Tests

- SPA/frontend automated tests (no runner exists); only manual checks `TC-MAN-FLOW-*` and `TC-MAN-UI-001`.
- Performance, load and soak tests; Cloud Run autoscaling; Neon connection limits.
- Dynamic security scanning (OWASP ZAP) and penetration testing; CI pipeline tests (CodeQL, Trivy, Gitleaks).
- Real Cloudinary, Neon or Google Cloud calls in the automated suite.
- Email deliverability (addresses are format-checked only) and phone number format beyond length.
- Cross-browser, accessibility and visual regression testing.
- Features the product does not have: password reset, profile edit, account deletion, notifications, email verification, token refresh/revocation.
- Re-testing behaviour already covered by the existing 43 tests (listed in section 6).
- Behaviour listed under Open Questions (no test is written until the expected result is confirmed).

## 14. Test Execution Order

Commands are shown for reference; **nothing has been run** and nothing will be until you confirm. Run from `backend/` with the dev dependencies installed (`pip install -r requirements-dev.txt`).

1. **Service tests** (fastest, no HTTP): `test_service_config.py` -> `test_service_auth.py` -> `test_service_rate_limit.py` -> `test_service_cloudinary.py` -> `test_service_cleanup_migration.py`.
2. **Validation tests:** `test_validation_schemas.py`.
3. **Data-integrity tests:** `test_data_integrity.py`.
4. **API tests**, in dependency order: `test_api_auth_flows.py` -> `test_api_users.py` -> `test_api_listings.py` -> `test_api_needs.py` -> `test_api_interests.py` -> `test_api_admin.py`.
5. **Existing regression suites:** `test_auth.py`, `test_authorization.py`, `test_input_validation.py`, `test_security_headers.py`.
6. **Manual verification** (section 11) after the automated suite is green and the change is on a staging deployment.

Suggested first run (after approval): `python -m pytest tests/test_service_*.py tests/test_validation_schemas.py tests/test_data_integrity.py -q`, then `python -m pytest tests/test_api_*.py -q`, then the full `python -m pytest -q`. Tests are independent (each starts with fresh tables and limiters), so order does not affect results; the order above is for fastest feedback and easiest diagnosis.

## 15. Coverage matrix

### 15.1 Totals

| Measure | Value |
| --- | --- |
| New test functions | 277 (service 63, API 169, validation 27, data integrity 18) |
| By kind | positive 67, negative 79, boundary 75, business 56 |
| Existing regression tests | 43 |
| Manual scenarios | 16 |
| Acceptance criteria (derived) | 78; with no automated or manual coverage: none |

### 15.2 Acceptance criteria x test kind

| AC | Positive | Negative | Boundary | Business | Existing | Manual | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AC-01.1 | 1 | 0 | 0 | 1 | 2 | 1 | Covered |
| AC-01.2 | 0 | 2 | 2 | 2 | 1 | 0 | Covered |
| AC-01.3 | 0 | 2 | 1 | 2 | 0 | 0 | Covered |
| AC-01.4 | 3 | 0 | 2 | 2 | 3 | 0 | Covered |
| AC-01.5 | 1 | 3 | 2 | 1 | 2 | 0 | Covered |
| AC-01.6 | 2 | 1 | 0 | 0 | 0 | 0 | Covered |
| AC-02.1 | 6 | 0 | 1 | 1 | 1 | 0 | Covered |
| AC-02.2 | 0 | 3 | 4 | 1 | 1 | 0 | Covered |
| AC-02.3 | 0 | 0 | 1 | 0 | 0 | 0 | Covered |
| AC-02.4 | 1 | 1 | 1 | 1 | 1 | 1 | Covered |
| AC-03.1 | 3 | 0 | 0 | 0 | 2 | 0 | Covered |
| AC-03.2 | 0 | 10 | 0 | 0 | 3 | 1 | Covered |
| AC-03.3 | 0 | 2 | 0 | 1 | 1 | 0 | Covered |
| AC-04.1 | 2 | 0 | 0 | 2 | 0 | 1 | Covered |
| AC-04.2 | 1 | 1 | 1 | 2 | 0 | 0 | Covered |
| AC-04.3 | 0 | 1 | 1 | 1 | 0 | 1 | Covered |
| AC-04.4 | 1 | 0 | 1 | 3 | 0 | 0 | Covered |
| AC-04.5 | 3 | 1 | 2 | 0 | 0 | 2 | Covered |
| AC-04.6 | 0 | 1 | 1 | 0 | 0 | 0 | Covered |
| AC-05.1 | 0 | 0 | 1 | 2 | 0 | 0 | Covered |
| AC-05.2 | 2 | 0 | 1 | 0 | 2 | 0 | Covered |
| AC-05.3 | 0 | 0 | 3 | 1 | 0 | 0 | Covered |
| AC-05.4 | 0 | 0 | 0 | 1 | 0 | 0 | Covered |
| AC-05.5 | 1 | 0 | 1 | 0 | 0 | 0 | Covered |
| AC-06.1 | 1 | 2 | 1 | 0 | 0 | 0 | Covered |
| AC-06.2 | 0 | 1 | 1 | 1 | 0 | 0 | Covered |
| AC-07.1 | 1 | 0 | 2 | 2 | 1 | 0 | Covered |
| AC-07.2 | 0 | 3 | 0 | 0 | 2 | 0 | Covered |
| AC-07.3 | 0 | 1 | 3 | 0 | 0 | 0 | Covered |
| AC-07.4 | 3 | 0 | 0 | 1 | 0 | 1 | Covered |
| AC-08.1 | 1 | 1 | 0 | 1 | 0 | 0 | Covered |
| AC-08.2 | 2 | 3 | 3 | 1 | 0 | 0 | Covered |
| AC-08.3 | 0 | 0 | 0 | 2 | 0 | 0 | Covered |
| AC-08.4 | 1 | 0 | 2 | 2 | 0 | 0 | Covered |
| AC-08.5 | 1 | 2 | 1 | 1 | 0 | 0 | Covered |
| AC-08.6 | 1 | 2 | 0 | 0 | 0 | 0 | Covered |
| AC-08.7 | 0 | 0 | 2 | 0 | 0 | 0 | Covered |
| AC-09.1 | 3 | 0 | 4 | 1 | 0 | 1 | Covered |
| AC-09.2 | 1 | 4 | 1 | 1 | 1 | 0 | Covered |
| AC-09.3 | 2 | 1 | 1 | 2 | 0 | 0 | Covered |
| AC-09.4 | 1 | 4 | 0 | 1 | 0 | 1 | Covered |
| AC-09.5 | 0 | 0 | 0 | 2 | 0 | 0 | Covered |
| AC-10.1 | 1 | 0 | 0 | 1 | 1 | 1 | Covered |
| AC-10.2 | 0 | 3 | 0 | 0 | 2 | 0 | Covered |
| AC-10.3 | 1 | 0 | 1 | 0 | 0 | 0 | Covered |
| AC-10.4 | 0 | 0 | 0 | 2 | 0 | 0 | Covered |
| AC-11.1 | 1 | 1 | 1 | 2 | 0 | 0 | Covered |
| AC-12.1 | 0 | 3 | 0 | 0 | 2 | 1 | Covered |
| AC-12.2 | 1 | 0 | 1 | 0 | 1 | 1 | Covered |
| AC-12.3 | 2 | 0 | 2 | 0 | 0 | 1 | Covered |
| AC-12.4 | 3 | 3 | 0 | 2 | 0 | 1 | Covered |
| AC-12.5 | 4 | 3 | 1 | 0 | 0 | 1 | Covered |
| AC-12.6 | 2 | 1 | 1 | 0 | 0 | 1 | Covered |
| AC-12.7 | 1 | 0 | 1 | 0 | 0 | 1 | Covered |
| AC-13.1 | 4 | 0 | 0 | 1 | 0 | 2 | Covered |
| AC-13.2 | 0 | 0 | 1 | 0 | 0 | 1 | Covered |
| AC-13.3 | 0 | 0 | 3 | 1 | 0 | 1 | Covered |
| AC-14.1 | 2 | 0 | 2 | 2 | 0 | 2 | Covered |
| AC-14.2 | 0 | 1 | 0 | 0 | 0 | 0 | Covered |
| AC-15.1 | 2 | 1 | 4 | 3 | 3 | 1 | Covered |
| AC-15.2 | 0 | 1 | 0 | 1 | 0 | 0 | Covered |
| AC-16.1 | 3 | 5 | 4 | 0 | 0 | 2 | Covered |
| AC-16.2 | 1 | 0 | 0 | 0 | 0 | 1 | Covered |
| AC-17.1 | 0 | 0 | 0 | 1 | 5 | 1 | Covered |
| AC-17.2 | 0 | 0 | 0 | 0 | 2 | 0 | Covered |
| AC-17.3 | 0 | 0 | 2 | 0 | 3 | 1 | Covered |
| AC-17.4 | 0 | 0 | 0 | 0 | 0 | 1 | Manual only |
| AC-18.1 | 3 | 1 | 0 | 1 | 0 | 0 | Covered |
| AC-18.2 | 0 | 0 | 0 | 0 | 1 | 0 | Covered |
| AC-19.1 | 0 | 4 | 1 | 2 | 0 | 0 | Covered |
| AC-19.2 | 4 | 0 | 0 | 1 | 0 | 0 | Covered |
| AC-19.3 | 4 | 1 | 1 | 3 | 0 | 2 | Covered |
| AC-19.4 | 1 | 0 | 1 | 1 | 0 | 1 | Covered |
| AC-19.5 | 0 | 1 | 1 | 1 | 0 | 1 | Covered |
| AC-19.6 | 2 | 0 | 0 | 1 | 0 | 0 | Covered |
| AC-20.1 | 0 | 1 | 0 | 1 | 0 | 0 | Covered |
| AC-20.2 | 3 | 0 | 0 | 1 | 0 | 0 | Covered |
| AC-20.3 | 0 | 0 | 3 | 0 | 0 | 0 | Covered |

### 15.3 Tasks x tests

Kind column order: positive/negative/boundary/business.

| Task | Description | New tests | P/N/B/Bz | Files |
| --- | --- | --- | --- | --- |
| T01 | Settings and configuration (app/config.py) | 9 | 3/1/3/2 | test_service_config.py |
| T02 | Database session and ORM models (database.py, models/) | 13 | 7/3/2/1 | test_data_integrity.py |
| T03 | Alembic migrations and startup migration service | 6 | 1/1/2/2 | test_service_cleanup_migration.py |
| T04 | Password hashing and JWT service (services/auth.py) | 16 | 5/7/3/1 | test_service_auth.py |
| T05 | Auth router: register, login, me (routers/auth.py) | 35 | 5/11/10/9 | test_api_auth_flows.py, test_data_integrity.py, test_validation_schemas.py |
| T06 | Auth dependencies: current user and admin (dependencies.py) | 8 | 1/6/0/1 | test_api_admin.py, test_api_auth_flows.py |
| T07 | Users router: profile and summary (routers/users.py) | 6 | 2/1/1/2 | test_api_auth_flows.py, test_api_users.py, test_data_integrity.py |
| T08 | Listings router (routers/listings.py) | 53 | 8/11/19/15 | test_api_listings.py, test_data_integrity.py, test_validation_schemas.py |
| T09 | Cloudinary image service (services/cloudinary.py) | 16 | 6/6/4/0 | test_api_listings.py, test_service_cloudinary.py |
| T10 | Interests router (routers/interests.py) | 33 | 7/13/7/6 | test_api_interests.py, test_data_integrity.py, test_validation_schemas.py |
| T11 | Needs router (routers/needs.py) | 29 | 6/8/8/7 | test_api_needs.py, test_validation_schemas.py |
| T12 | Admin router and audit log (routers/admin.py) | 36 | 12/10/10/4 | test_api_admin.py, test_data_integrity.py |
| T13 | Rate limiting service (services/rate_limit.py) | 19 | 2/2/11/4 | test_api_admin.py, test_api_interests.py, test_api_listings.py, test_api_needs.py, test_service_rate_limit.py |
| T14 | Security headers and request-id middleware (middleware.py) | 0 | 0/0/0/0 | (existing suites only) |
| T15 | Expiry cleanup service (services/cleanup.py) | 7 | 2/1/2/2 | test_service_cleanup_migration.py |
| T16 | Global exception handlers and validation errors (main.py) | 5 | 3/1/0/1 | test_validation_schemas.py |

### 15.4 Endpoints x tests

| Method | Path | Auth | Success | Acceptance criteria | New API tests |
| --- | --- | --- | --- | --- | --- |
| POST | /api/auth/register | public | 201 | AC-01.1..01.6 | 13 |
| POST | /api/auth/login | public | 200 | AC-02.1..02.4 | 10 |
| GET | /api/auth/me | user | 200 | AC-03.1, AC-03.2, AC-03.3 | 9 |
| GET | /api/users/me | user | 200 | AC-03.1 | 2 |
| GET | /api/users/me/summary | user | 200 | AC-11.1 | 4 |
| POST | /api/listings | user | 201 | AC-04.1..04.6, AC-16.1 | 20 |
| GET | /api/listings | public | 200 | AC-05.1..05.5 | 12 |
| GET | /api/listings/me | user | 200 | AC-06.2 | 3 |
| GET | /api/listings/{id} | public | 200 | AC-06.1 | 4 |
| PUT | /api/listings/{id} | owner | 200 | AC-07.1..07.3 | 7 |
| DELETE | /api/listings/{id} | owner | 200 | AC-07.2, AC-07.4 | 5 |
| POST | /api/interests/listing/{id} | user | 201 | AC-09.1, AC-09.2 | 12 |
| GET | /api/interests/received | user | 200 | AC-09.3 | 6 |
| GET | /api/interests/sent | user | 200 | AC-09.3 | 6 |
| PATCH | /api/interests/{id}/accept | listing owner | 200 | AC-09.4, AC-09.5 | 8 |
| PATCH | /api/interests/{id}/reject | listing owner | 200 | AC-09.4 | 6 |
| GET | /api/interests/{id}/contact | participant | 200 | AC-10.1..10.3 | 6 |
| POST | /api/needs | user | 201 | AC-08.1..08.3, AC-08.7 | 12 |
| GET | /api/needs | public | 200 | AC-08.4, AC-08.7 | 7 |
| GET | /api/needs/me | user | 200 | AC-08.5 | 5 |
| GET | /api/needs/{id} | public | 200 | AC-08.5 | 5 |
| DELETE | /api/needs/{id} | owner | 200 | AC-08.6 | 3 |
| GET | /api/admin/stats | admin | 200 | AC-12.1, AC-12.2 | 5 |
| GET | /api/admin/users | admin | 200 | AC-12.3 | 4 |
| PATCH | /api/admin/users/{id} | admin | 200 | AC-12.4, AC-13.1, AC-13.2 | 12 |
| GET | /api/admin/listings | admin | 200 | AC-12.5 | 8 |
| PATCH | /api/admin/listings/{id}/status?status= | admin | 200 | AC-12.5, AC-13.1 | 10 |
| DELETE | /api/admin/listings/{id} | admin | 200 | AC-12.5, AC-13.1 | 10 |
| GET | /api/admin/needs | admin | 200 | AC-12.6 | 4 |
| DELETE | /api/admin/needs/{id} | admin | 200 | AC-12.6, AC-13.1 | 7 |
| GET | /api/admin/audit-logs | admin | 200 | AC-13.3 | 4 |

### 15.5 Files

| Test file | New test functions |
| --- | --- |
| test_api_admin.py | 35 |
| test_api_auth_flows.py | 28 |
| test_api_interests.py | 30 |
| test_api_listings.py | 47 |
| test_api_needs.py | 25 |
| test_api_users.py | 4 |
| test_data_integrity.py | 18 |
| test_service_auth.py | 16 |
| test_service_cleanup_migration.py | 13 |
| test_service_cloudinary.py | 13 |
| test_service_config.py | 9 |
| test_service_rate_limit.py | 12 |
| test_validation_schemas.py | 27 |

## 16. Open questions

These were unclear or contradictory in the derived baseline. No test asserts a result for them; confirm the intended behaviour and tests can be added.

1. **Missing artifacts:** should the derived AC/FR/T IDs be replaced by the IDs in the real spec.md/tasks.md once they exist?
2. **Login for deactivated users:** `/auth/login` currently issues a token and the user is refused only on later calls. Should login itself return 403?
3. **Admin deleting a listing:** should the listing's Cloudinary images be deleted too? Today they are not (owner delete and cleanup do delete them).
4. **Owner delete when Cloudinary fails:** should the listing still be deleted (best effort) or the request fail? Today the request returns 500 and the listing remains.
5. **Visibility of non-active listings:** should `GET /listings/{id}` return SOLD/RENTED/UNAVAILABLE listings to anyone? Today it does; only expired-ACTIVE returns 404 (`TC-API-LST-052`).
6. **Listing update rules:** are there length limits for location/description/price_unit on update, must price follow the SELL/RENT rule, and may an owner set any status (including back to ACTIVE)? Only title, price and enum validity are tested.
7. **Cleanup scope:** `TC-SVC-CLN-004` assumes expired listings/needs are removed regardless of status. Confirm.
8. **Exact-expiry instant:** cleanup uses `expires_at <= now` while visibility uses `expires_at > now`; behaviour at exactly `expires_at` is untested.
9. **Accepting an interest:** should it affect the listing (e.g. reserve it) or other pending interests? `TC-API-INT-035/036` assert today's behaviour (no effect, several accepts allowed).
10. **Duplicate-submission response:** should a replayed create return 201, 200 or 409? Tests assert only that the same record is returned and no new row is created.
11. **Rate-limit scope:** tests assume per-process limits keyed by client IP, with failed and successful attempts both counted. Is that the intended contract, and is the trusted client-IP source specified?
12. **HSTS in production:** the deploy workflow sets `HSTS_ENABLED=true` but the live API did not send the header on 2026-11-12 (see `tasks.md`). Which is the expected state? Manual check `TC-MAN-SEC-002` records it.
13. **Phone and name formats:** only lengths are specified; are digits-only or `+` prefixes required? Is leading/trailing whitespace in passwords allowed?
14. **Duplicate precedence:** when both email and phone already exist, which 409 message is expected? (Today: email first; untested.)
15. **Pagination for "mine" lists:** the SPA relies on the API's default page of 20; is that intended? Tests assert the API behaviour only.
16. **Need statuses:** `FULFILLED`/`CLOSED` cannot be set through the API; browse tests set them directly in the DB. Should an endpoint exist?
17. **SQLite vs PostgreSQL:** `ILIKE` and case-insensitive search are tested with ASCII text on SQLite; any Postgres-specific collation expectations should be confirmed.
18. **Unrelated parent instructions:** `D:\Asus\CLAUDE.md` belongs to another project; ignored here.

---

## Appendix A - Derived baseline

### A.1 Functional requirements and acceptance criteria

**FR-01 - User registration**

- AC-01.1: Valid registration returns 201 with the profile and no password data.
- AC-01.2: Only emails from the allowed domain list (default gmail.com) are accepted; exact, case-insensitive domain match.
- AC-01.3: Email and phone must be unique; duplicates return 409.
- AC-01.4: Password is 8-100 characters with at least one letter and one digit, stored as an Argon2id hash.
- AC-01.5: Field limits: name 2-100, phone 10-15, valid role and joining date; text is trimmed.
- AC-01.6: New accounts are non-admin and active; clients cannot set these flags.

**FR-02 - Login and token issuance**

- AC-02.1: Valid credentials return a bearer JWT for that user.
- AC-02.2: Invalid credentials return an identical 401 regardless of cause; malformed bodies are 422.
- AC-02.3: Login email is case-insensitive.
- AC-02.4: Login is throttled per IP and per account (10 per 60 s) with 429 + Retry-After.

**FR-03 - Authenticated identity and account state**

- AC-03.1: /api/auth/me and /api/users/me return the caller's profile.
- AC-03.2: Missing, malformed, expired, forged or unknown-user tokens are rejected (401/403).
- AC-03.3: Deactivated accounts receive 403 on every protected endpoint.

**FR-04 - Create listing**

- AC-04.1: Valid listing creation returns 201, status ACTIVE, owned by the caller, expiring after 30 days.
- AC-04.2: Pricing: SELL and RENT need price > 0; LEND/GIVEAWAY force price 0 and no unit; RENT defaults unit to 'day'.
- AC-04.3: Field limits: title 2-150, location 2-100, description 2-2000, price >= 0, valid enums; text is trimmed.
- AC-04.4: An identical submission by the same owner within 60 s returns the existing listing.
- AC-04.5: At most 5 images; an upload failure rolls back the listing and removes already-uploaded images.
- AC-04.6: Creation requires authentication and is throttled.

**FR-05 - Browse and search listings**

- AC-05.1: Public browse returns only ACTIVE, unexpired listings.
- AC-05.2: Filters: title search, category, type, condition, location, inclusive price range.
- AC-05.3: Newest first; skip >= 0; limit 1-100 (default 20).
- AC-05.4: List items show owner name/role and first image and never contact details.
- AC-05.5: Browse is throttled.

**FR-06 - Listing detail and my listings**

- AC-06.1: Detail returns the listing with images; 404 for unknown or expired-active listings.
- AC-06.2: /listings/me returns only the caller's listings (any status) and requires authentication.

**FR-07 - Owner edit and delete of listings**

- AC-07.1: The owner can partially update a listing; unspecified fields stay unchanged.
- AC-07.2: Non-owners get 403, unknown listings 404, anonymous callers 401/403.
- AC-07.3: Update validation: title 2-150, price >= 0, valid enums.
- AC-07.4: Deleting a listing removes its images (including Cloudinary assets) and interests.

**FR-08 - Needs (requests)**

- AC-08.1: Valid need creation returns 201, status ACTIVE, expiring after 30 days.
- AC-08.2: Need limits: title 2-150, location 2-100, description 2-2000, duration <= 100, budget >= 0, valid enums.
- AC-08.3: An identical need within 60 s returns the existing record.
- AC-08.4: Public need browse returns ACTIVE, unexpired needs with filters, ordering and pagination.
- AC-08.5: /needs/me lists own needs; detail is public; 404 for unknown or expired-active needs.
- AC-08.6: Only the owner can delete a need.
- AC-08.7: Need creation and browsing are throttled.

**FR-09 - Interests and owner decisions**

- AC-09.1: Expressing interest creates a PENDING interest; message optional, at most 500 characters.
- AC-09.2: Interest is refused for own, missing, inactive or expired listings and for duplicates (409).
- AC-09.3: Sent and received lists are scoped to the caller, enriched with names/titles, ordered and paginated.
- AC-09.4: Only the listing owner can accept/reject, and only PENDING interests.
- AC-09.5: Accepting does not change the listing or other interests.

**FR-10 - Contact reveal**

- AC-10.1: Contact details are returned only for ACCEPTED interests, only to the two participants, as the counterpart's name, email and phone.
- AC-10.2: Contact is refused for pending/rejected interests, non-participants, unknown ids and anonymous callers.
- AC-10.3: Contact reveal is throttled.
- AC-10.4: Contact details never appear in any other payload.

**FR-11 - Activity summary**

- AC-11.1: The summary returns accurate listing, need, sent, received and pending-received counters.

**FR-12 - Admin moderation**

- AC-12.1: Every admin route requires an active admin (403 members, 401/403 anonymous).
- AC-12.2: Stats report total and active counts for users, listings, needs and interests.
- AC-12.3: Admin user list supports search and pagination (limit 1-200) without secrets.
- AC-12.4: Admins can activate/deactivate users and grant/revoke admin; self-demotion is refused; unknown user is 404.
- AC-12.5: Admins can list/filter listings, change status, and delete listings.
- AC-12.6: Admins can list/filter needs and delete needs.
- AC-12.7: Admin routes are throttled.

**FR-13 - Admin audit trail**

- AC-13.1: Each effective admin mutation writes an audit entry (actor, action, target, IP, details).
- AC-13.2: Unchanged/no-op admin updates write no audit entry.
- AC-13.3: The audit log is newest first, paginated (limit 1-100) and shows the actor name.

**FR-14 - Expiry cleanup**

- AC-14.1: Cleanup deletes expired listings (and their Cloudinary assets) and expired needs and keeps current ones.
- AC-14.2: A Cloudinary failure during cleanup does not stop the run.

**FR-15 - Rate limiting**

- AC-15.1: Sliding-window limiter: per-key counting, 429 with Retry-After, window expiry.
- AC-15.2: Per-account limiter keys are hashed and case-insensitive.

**FR-16 - Image validation and storage**

- AC-16.1: Only JPEG/PNG/WebP by declared type and magic bytes, within the size limit.
- AC-16.2: Images are stored under a per-listing Cloudinary folder.

**FR-17 - Response security (headers, CORS, request id)**

- AC-17.1: Security headers are set on responses (HSTS only when enabled; no-store on sensitive paths; CSP exemptions for docs).
- AC-17.2: A safe client X-Request-ID is echoed; otherwise one is generated.
- AC-17.3: CORS allows only configured origins, never a wildcard.
- AC-17.4: API documentation endpoints are disabled in production.

**FR-18 - Error handling**

- AC-18.1: Validation failures return 422 with a readable detail (string for one error, list for several) and never echo secrets.
- AC-18.2: Unexpected server errors return a generic 500 without internal details.

**FR-19 - Data integrity and migrations**

- AC-19.1: Uniqueness is enforced for email, phone and (listing, user) interest.
- AC-19.2: Defaults and enum values persist correctly.
- AC-19.3: Deleting a parent removes dependent records; unrelated records are untouched.
- AC-19.4: Startup migrations build the full schema at head and are idempotent; the unpooled URL is preferred.
- AC-19.5: Migration failure is fatal in production and tolerated elsewhere.
- AC-19.6: Passwords are never stored or returned in plaintext.

**FR-20 - Configuration**

- AC-20.1: Required settings are mandatory.
- AC-20.2: Documented defaults apply when settings are absent.
- AC-20.3: Comma-separated settings are parsed, trimmed and normalised.

### A.2 Implementation tasks

| Task | Module / responsibility |
| --- | --- |
| T01 | Settings and configuration (app/config.py) |
| T02 | Database session and ORM models (database.py, models/) |
| T03 | Alembic migrations and startup migration service |
| T04 | Password hashing and JWT service (services/auth.py) |
| T05 | Auth router: register, login, me (routers/auth.py) |
| T06 | Auth dependencies: current user and admin (dependencies.py) |
| T07 | Users router: profile and summary (routers/users.py) |
| T08 | Listings router (routers/listings.py) |
| T09 | Cloudinary image service (services/cloudinary.py) |
| T10 | Interests router (routers/interests.py) |
| T11 | Needs router (routers/needs.py) |
| T12 | Admin router and audit log (routers/admin.py) |
| T13 | Rate limiting service (services/rate_limit.py) |
| T14 | Security headers and request-id middleware (middleware.py) |
| T15 | Expiry cleanup service (services/cleanup.py) |
| T16 | Global exception handlers and validation errors (main.py) |

### A.3 API contract (derived from routes and schemas)

| Method | Path | Auth | Success | Acceptance criteria | Tasks |
| --- | --- | --- | --- | --- | --- |
| POST | /api/auth/register | public | 201 | AC-01.1..01.6 | T05 |
| POST | /api/auth/login | public | 200 | AC-02.1..02.4 | T05 |
| GET | /api/auth/me | user | 200 | AC-03.1, AC-03.2, AC-03.3 | T05, T06 |
| GET | /api/users/me | user | 200 | AC-03.1 | T07 |
| GET | /api/users/me/summary | user | 200 | AC-11.1 | T07 |
| POST | /api/listings | user | 201 | AC-04.1..04.6, AC-16.1 | T08, T09 |
| GET | /api/listings | public | 200 | AC-05.1..05.5 | T08 |
| GET | /api/listings/me | user | 200 | AC-06.2 | T08 |
| GET | /api/listings/{id} | public | 200 | AC-06.1 | T08 |
| PUT | /api/listings/{id} | owner | 200 | AC-07.1..07.3 | T08 |
| DELETE | /api/listings/{id} | owner | 200 | AC-07.2, AC-07.4 | T08, T09 |
| POST | /api/interests/listing/{id} | user | 201 | AC-09.1, AC-09.2 | T10 |
| GET | /api/interests/received | user | 200 | AC-09.3 | T10 |
| GET | /api/interests/sent | user | 200 | AC-09.3 | T10 |
| PATCH | /api/interests/{id}/accept | listing owner | 200 | AC-09.4, AC-09.5 | T10 |
| PATCH | /api/interests/{id}/reject | listing owner | 200 | AC-09.4 | T10 |
| GET | /api/interests/{id}/contact | participant | 200 | AC-10.1..10.3 | T10 |
| POST | /api/needs | user | 201 | AC-08.1..08.3, AC-08.7 | T11 |
| GET | /api/needs | public | 200 | AC-08.4, AC-08.7 | T11 |
| GET | /api/needs/me | user | 200 | AC-08.5 | T11 |
| GET | /api/needs/{id} | public | 200 | AC-08.5 | T11 |
| DELETE | /api/needs/{id} | owner | 200 | AC-08.6 | T11 |
| GET | /api/admin/stats | admin | 200 | AC-12.1, AC-12.2 | T12 |
| GET | /api/admin/users | admin | 200 | AC-12.3 | T12 |
| PATCH | /api/admin/users/{id} | admin | 200 | AC-12.4, AC-13.1, AC-13.2 | T12 |
| GET | /api/admin/listings | admin | 200 | AC-12.5 | T12 |
| PATCH | /api/admin/listings/{id}/status?status= | admin | 200 | AC-12.5, AC-13.1 | T12 |
| DELETE | /api/admin/listings/{id} | admin | 200 | AC-12.5, AC-13.1 | T12 |
| GET | /api/admin/needs | admin | 200 | AC-12.6 | T12 |
| DELETE | /api/admin/needs/{id} | admin | 200 | AC-12.6, AC-13.1 | T12 |
| GET | /api/admin/audit-logs | admin | 200 | AC-13.3 | T12 |

Common error responses: `401/403` (no or invalid token), `403` (forbidden, deactivated, not admin), `404` (missing), `409` (conflict), `422` (validation; `detail` is a string for one error and a list for several), `429` with `Retry-After` (throttled), `500` generic. Full details: `wiki/API-Reference.md`.

---

## 17. Additions: Google sign-in and profile editing

Added after the baseline above was written. These are **requirements stated by the product owner in conversation**, not part of the derived baseline, so they carry two new derived groups: **AC-21.x** (Google sign-in) and **AC-22.x** (profile completion and editing). Task IDs are all T05 (users and auth) or the endpoint's own task.

| Group | Criterion (derived from the stated behaviour) |
| --- | --- |
| AC-21.1 | First Google sign-in creates an account with name and email only, no password |
| AC-21.2 | A returning Google account maps to the same user; a deactivated user is refused |
| AC-21.3 | An existing password account with the same email is **not** merged (409) |
| AC-21.4 | The same email-domain rule as registration applies |
| AC-21.5 | The ID token is verified: signature, audience, issuer, expiry, verified email; every failure is one generic 401 |
| AC-21.6 | With no `GOOGLE_CLIENT_ID`, or Google unreachable, the endpoint answers 503 |
| AC-21.7 | Google sign-in is rate limited with the login bucket |
| AC-21.8 | A Google-only account cannot log in with a password |
| AC-22.1 | `complete-profile` stores phone, role and joining date and marks the profile complete |
| AC-22.2 | Until complete, posting an item or request and sending an enquiry are refused (403); reading is not |
| AC-22.3 | Completing twice, or editing before completing, is 409 |
| AC-22.4 | Phone is 10 to 15 digits and unique; role is a defined value; joining date is not in the future; no extra fields |
| AC-22.5 | `PATCH /users/me` changes role and/or joining date, only for the caller |
| AC-22.6 | Name, email, phone and `is_admin` cannot be edited (422) |

| File | Tests | Covers |
| --- | --- | --- |
| `backend/tests/test_service_google.py` | 19 collected | Token verifier with a throwaway RSA key: valid, bare issuer, clock skew, wrong audience / expiry / issuer, unverified or missing claims, forged signature, `alg=none`, HS256 confusion, garbage, not configured, Google unreachable |
| `backend/tests/test_api_google_auth.py` | 28 collected | `POST /auth/google` and the incomplete-profile gate |
| `backend/tests/test_api_profile.py` | 40 collected | `complete-profile` and `PATCH /users/me` |

Google's servers are never contacted by these tests: the verifier is stubbed at the router, and tested separately with locally signed tokens.

**Not covered automatically:** the real round trip with Google (needs a real OAuth client ID and a browser) and the Postgres behaviour of the new migration (`b7c41d9e5a20`). Both belong with the manual checks in section 11: sign in with a real Google account on staging, and run the migration against a Neon branch before production.

### Frontend

The frontend still has no test runner. This round of UI work was verified by driving a real Chrome with throwaway Playwright scripts against a local backend (SQLite scratch database): registration and login validation, posting an item and a request, enquiry, accept and contact reveal, profile edit, the complete-profile flow, every admin tab, and phone-width layouts. Those scripts were not added to the repository. If you want them kept, they are the starting point for an end-to-end suite.
