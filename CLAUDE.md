# CLAUDE.md

Guidance for AI assistants working in this repo. Short on purpose: the code and `wiki/` are the source of truth; this file is the rules of engagement.

**InfyExchange** – a marketplace for Infosys Mysore trainees (sell / rent / lend / give away, plus "needs"). React SPA → FastAPI API → Postgres, with Cloudinary for images.

**It is live.** Web: <https://infyexchange.pages.dev/> (Cloudflare Pages). API: Google Cloud Run. DB: Neon. Treat every change as one that real users will receive.

> **Scope note.** A `CLAUDE.md` in a parent directory (`d:\Asus\`) belongs to a different project (`fraud_hunter_env`, an OpenEnv hackathon). Ignore it here. In *this* repo, `docs/security/` and `wiki/` **are** authoritative and should be read and kept current.

---

## How to work (read this first)

These four habits matter more than any rule below.

**1. Think before coding.** State your assumptions. If a request has two plausible readings, or something looks wrong, say so and ask – don't silently pick one. If a simpler approach exists, propose it. Read the relevant code *before* proposing a change; don't pattern-match from how "a typical FastAPI app" works.

**2. Simplicity first.** Write the least code that solves the stated problem. No speculative features, abstractions for single use, config knobs nobody asked for, or error handling for impossible states. If 200 lines could be 50, write 50. This codebase deliberately has no repository layer, no state library, no CSS framework – don't introduce one to solve a local problem.

**3. Surgical changes.** Touch only what the task requires. Match the surrounding style, even where you'd do it differently. Don't reformat, rename, or "improve" adjacent code. Clean up only the mess *your* change creates (unused imports you left behind). If you notice unrelated problems, mention them – don't fix them in the same diff. Every changed line should trace to the request.

**4. Goal-driven execution.** Turn the task into a verifiable outcome, then loop until it's verified:
- "Fix the bug" → write a failing test that reproduces it, then make it pass.
- "Add validation" → tests for the invalid inputs, then the code.
- "Refactor X" → tests pass before and after.
For multi-step work, state a short plan with a check per step. Don't claim "done" without running the check; if you couldn't run something, say so plainly.

---

## Commands

Backend (run **from `backend/`** – `.env` and `alembic.ini` resolve relative to the working directory):

```powershell
pip install -r requirements-dev.txt        # runtime + test/security tooling (prod image uses requirements.txt only)
docker compose up -d                       # local Postgres 17 on 127.0.0.1:5432
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
python -m pytest -q                        # ~790 tests, ~7 min; SQLite, no Docker needed. Pass DATABASE_URL_UNPOOLED="" so tests never touch the .env database
python -m bandit -r app -q
python -m pip_audit -r requirements.txt --progress-spinner off
alembic revision --autogenerate -m "msg"  # then REVIEW the file
python -m app.run_cleanup                  # one-shot expiry cleanup
```

Frontend (repo root):

```powershell
npm ci
npm run dev          # http://127.0.0.1:5173, proxies /api -> :8000
npm run build        # must pass; also generates dist/_headers
```

Other: `python scripts/security/openapi_diff.py` (offered-vs-consumed API routes), `scripts/security/zap-api-scan.ps1` (staging only).

There is no frontend test runner or linter. **Before saying a change works:** backend changes → `pytest` (+ `bandit` if you touched security code); frontend changes → `npm run build` and, for UI behaviour, actually run it in the browser.

---

## Map

```
src/                 React 19 + Vite 8. pages/ (screens) · components/ · hooks/useForm.js · context/AuthContext.jsx · services/api.js · utils/ (labels.js = enum to text, validate.js = form rules, filters.js)
backend/app/         routers/ (HTTP + business rules) · models/ · schemas/ · services/ · dependencies.py · middleware.py · config.py · main.py
backend/alembic/     four revisions: ee1edd3df3f3 -> b7c41d9e5a20 -> c3a8f1d27b64 (enquiry flow, chat, bell) -> d5b2e9a14c70 (failed emails)
backend/tests/       conftest.py swaps in SQLite and disables the lifespan; tests/support.py = builders. New tests carry TC-/AC-/T ids in docstrings
test.md              Test plan (generated tables mirror those docstrings; derived baseline, not approved)
docs/security/       threat model, runbook, pipeline, asset inventory, acceptance criteria, test plan
wiki/                Detailed guide: start at wiki/Home.md
.github/workflows/   ci.yml · cloud-run-deploy.yml · pages-deploy.yml
```

Where to look for what: endpoints & rules → `wiki/API-Reference.md`; tables → `wiki/Data-Model.md`; flows → `wiki/Business-Rules-and-Flows.md`; env vars → `wiki/Configuration-Reference.md`; known bugs → `wiki/Known-Limitations-and-Gaps.md`.

---

## Invariants – do not break these

**Security**
- Every non-public route uses `Depends(get_current_user)`; admin routes inherit `get_current_admin` from the admin router. Ownership is checked explicitly (`owner_id != current_user.id → 403`). New write/reveal endpoints get a rate-limit bucket.
- **Contact details (email/phone) leave the API only via `GET /interests/{id}/contact`**, only for a chatting (`ACCEPTED`) enquiry or the deal winner, only to the listing owner or the interested user. Never add them to listing/interest/need/chat/notification payloads. The one exception is outside the API: the admin enquiry alert email carries the enquirer's address (reply-to), by decision.
- Never log or return passwords, tokens, DB URLs, Cloudinary secrets, or stack traces. Error `detail` strings are user-facing – keep them generic for server faults.
- JWT decoding keeps the algorithm pinned; password hashing stays Argon2id. CORS origins stay an explicit list – never `*`.
- Admin mutations call `log_admin_action(...)` before `db.commit()`.
- Google sign-in (`POST /auth/google`) verifies the ID token server-side (RS256 pinned, audience, issuer, `email_verified`) and **never auto-merges** with an existing password account. Accounts without phone/role/joining date can browse but cannot post or send enquiries (`get_complete_user`).
- Secrets live in Google Secret Manager / local `.env` (git-ignored). Never commit `.env`, tokens, or connection strings; never put secrets in `VITE_*` (they're public).
- Uploads: keep the type + size + magic-byte checks; images are 5 max, 5 MB each.

**Data**
- Schema changes go through an Alembic migration that stays **backward-compatible with the previous Cloud Run revision** (old code runs against the new schema during rollout). No drop/rename in the same release as the code change. Enum additions need an explicit `ALTER TYPE` – autogenerate misses them.
- Production runs migrations at startup under an advisory lock and aborts if they fail. Test a migration against real Postgres, not just SQLite.
- Timestamps are naive UTC (`datetime.utcnow()`); keep that consistent rather than mixing in aware datetimes.

**Frontend**
- `VITE_API_BASE_URL` must end in `/api` with no trailing slash (build enforces it) and is baked in at build time.
- Render user content through React only (no `dangerouslySetInnerHTML`). The JWT is in `localStorage`, so XSS is the main threat.
- Client validation (`src/utils/validate.js`) mirrors server limits (lengths, whole-rupee amounts, image count/size). Change both together; the server is authoritative.
- Never show an API code (`SELL`, `SP_L1`, `UPDATE_USER`) to a person: map it in `src/utils/labels.js`. Screens say "item" (listing), "request" (need) and "enquiry" (interest).
- CSP ships report-only (`CSP_ENFORCE=false` in `vite.config.js`). Don't flip it without the burn-in described in the runbook.

---

## Gotchas that waste time

- Starting uvicorn/pytest/alembic from the repo root fails to find `.env`/`alembic.ini`. `cd backend` first.
- Tests use SQLite: they won't catch Postgres-specific behaviour (native enums, `ILIKE`, advisory locks, varchar overflow → 500).
- Rate limiters are in-memory, per process. Tests clear them in the autouse fixture; if you add a limiter, add it to that list in `conftest.py`.
- No admin can be created via the API at first – set `is_admin` in the DB.
- `PUT /listings/{id}` and `DELETE /needs/{id}` exist but the SPA doesn't call them, and the API has no way to respond to a need. Don't assume UI parity with the API.
- `App.jsx`, `AuthContext.jsx`, `Cards.jsx`, `Ui.jsx`, `HomePage.jsx` are dense one-liners. Edit minimally; don't reformat unprompted (that's a separate, reviewable change).
- Admin listing deletion doesn't remove Cloudinary images (known bug, see wiki). Don't "fix" it as a drive-by unless asked – but don't copy the pattern.

---

## Ask first (outward-facing or hard to reverse)

- **Pushing is deploying.** A push to `deploy/neon-cloudrun-cloudflare-pages` runs CI and then (after `neon-staging` approval) updates the live Cloud Run service and Pages site. Never push, open PRs, force-push, rebase shared branches, or trigger workflows without being asked. Commit only when asked.
- Anything touching production data or infrastructure: Neon, Secret Manager, Cloud Run settings, Cloudflare, GitHub environments/secrets, Cloudinary assets. Prefer giving the user the exact command to run.
- Deleting files, dropping/renaming columns, rewriting history, dependency major-version bumps.
- Don't run ZAP or load tests against production. Use synthetic data only.

---

## Conventions

- Python 3.12, sync SQLAlchemy 2 style (`select(...)`, `db.scalar/scalars`), Pydantic 2 schemas with explicit `response_model`s, `HTTPException` with plain-English `detail`. Strip incoming strings before saving. Use eager loading (`joinedload`/`selectinload`) to avoid N+1.
- Business rules live inline in routers; keep functions small and guard-clause style rather than adding layers.
- React: function components + hooks, local state per page, all HTTP through `src/services/api.js`, enums as uppercase strings matching the backend.
- Dependencies are pinned and audited in CI. Add one only if the standard library or existing stack can't do the job, and say why.
- Comments explain *why* (constraints, security reasoning), not what the code says.

## Keep the docs true

If you change behaviour, update the matching wiki page in the same change (API shape → `API-Reference.md`; env var → `Configuration-Reference.md`; schema → `Data-Model.md`; fixed a listed bug → remove it from `Known-Limitations-and-Gaps.md`). Security-relevant changes also touch `docs/security/`. Mark claims you couldn't verify as such rather than stating them as fact.

## Communication

Be direct and concise. Lead with the result or the question. When you change something, say what and why in a few lines, and call out anything you did *not* verify. Disagree plainly when you think an approach is wrong – then do what the user decides.
