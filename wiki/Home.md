# InfyExchange Wiki

InfyExchange is a community marketplace for the Infosys Mysore trainee community. Members list items to **sell, rent, lend or give away**, post **needs** ("I'm looking for a squash racket"), and exchange contact details only after the owner accepts an interest request. Administrators moderate listings, needs and users, and every privileged action is audit-logged.

This wiki describes the code **as it exists on the `deploy/neon-cloudrun-cloudflare-pages` branch**. It complements (and does not replace) the shorter [README](../README.md) and the formal security documents in [docs/security/](../docs/security/).

## Production

The app is **deployed and live**: web at <https://infyexchange.pages.dev/> (Cloudflare Pages), API on Google Cloud Run (`asia-southeast1`), database on Neon PostgreSQL, images on Cloudinary. Checked 2026-11-12: `/health` returns healthy, `/docs` is disabled, CORS allows the Pages origin, and the SPA serves its generated security headers. One open check – the live API did not send `Strict-Transport-Security` (see [Operations](Operations-and-Troubleshooting.md#live-deployment-snapshot)). AI assistants should also read [CLAUDE.md](../CLAUDE.md).

## Start here

| If you want to… | Read |
| --- | --- |
| Get the app running on your machine | [Getting Started](Getting-Started.md) |
| Understand how the pieces fit together | [Architecture](Architecture.md) |
| Find an endpoint, its auth rules and limits | [API Reference](API-Reference.md) |
| See the tables, enums and relationships | [Data Model](Data-Model.md) |
| Work on the FastAPI service | [Backend Guide](Backend-Guide.md) |
| Work on the React app | [Frontend Guide](Frontend-Guide.md) |
| Understand how listings, interests and contact reveal behave | [Business Rules & Flows](Business-Rules-and-Flows.md) |
| Review authentication, headers, rate limits and threats | [Security](Security.md) |
| Look up an environment variable | [Configuration Reference](Configuration-Reference.md) |
| Understand CI/CD and deploy to production | [CI/CD & Deployment](CI-CD-and-Deployment.md) |
| Run, add or understand tests | [Testing](Testing.md) |
| Operate, debug or recover production | [Operations & Troubleshooting](Operations-and-Troubleshooting.md) |
| Know what is missing, risky or inconsistent | [Known Limitations & Gaps](Known-Limitations-and-Gaps.md) |
| Look up a term | [Glossary](Glossary.md) |

## Project at a glance

| Aspect | Detail |
| --- | --- |
| Frontend | React 19, React Router 7, Vite 8, `lucide-react` icons, a single hand-written `style.css` |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (sync), Pydantic 2, Alembic |
| Database | PostgreSQL (Neon in production, Docker Postgres 17 locally; SQLite in tests) |
| Media | Cloudinary (listing images only) |
| Auth | Email + password, Argon2id hashes, HS256 JWT bearer tokens (7-day default lifetime) |
| Hosting | Cloudflare Pages (SPA), Google Cloud Run (API), Neon (DB) |
| CI/CD | GitHub Actions; Workload Identity Federation to GCP; image scanned and deployed by digest |
| Size | ~99 tracked files: 6 routers, 6 ORM models, 43 backend tests, 8 security documents |

## Repository map

```text
.
├── README.md                    Short setup/deploy guide
├── wiki/                        This wiki
├── index.html                   Vite entry HTML
├── vite.config.js               Dev proxy, build-time API URL validation, _headers generation
├── neon.ts                      Neon CLI project config (branch TTL policy)
├── package.json / package-lock.json
├── .env.example                 Frontend env template (VITE_API_BASE_URL)
├── public/_redirects            Cloudflare Pages SPA fallback
├── images/                      Logo source files
├── src/                         React application
│   ├── main.jsx, app/App.jsx    Bootstrap + routes
│   ├── pages/                   One file per screen group
│   ├── components/              Layout, cards, UI bits, ErrorBoundary
│   ├── context/AuthContext.jsx  Token + current user state
│   ├── services/api.js          Fetch wrapper + endpoint catalogue
│   ├── utils/filters.js         Client-side filtering for "mine" lists
│   └── style.css
├── backend/
│   ├── Dockerfile, docker-compose.yml, requirements.txt (runtime), requirements-dev.txt, pytest.ini
│   ├── .env.example             Backend env template
│   ├── alembic.ini, alembic/    Migrations (one initial revision)
│   ├── app/
│   │   ├── main.py              App factory, middleware, error handlers, lifespan
│   │   ├── config.py            Pydantic settings
│   │   ├── database.py          Engine, session, Base
│   │   ├── dependencies.py      get_current_user / get_current_admin
│   │   ├── middleware.py        Request-ID + security headers
│   │   ├── models/ schemas/ routers/ services/ utils/
│   │   └── run_cleanup.py       One-shot expiry cleanup entry point
│   └── tests/                   pytest security suite
├── docs/security/               threat model, runbook, pipeline, asset inventory, test plan…
├── scripts/security/            ZAP scan wrapper, OpenAPI offered-vs-consumed diff
└── .github/                     CI, Cloud Run deploy, Pages deploy, Dependabot
```

## Conventions used in this wiki

- File and line references point at the working tree of this branch.
- **"Verified"** means the statement comes directly from reading the code; **"Inference"** marks conclusions drawn from it (for example, behaviour of Cloud Run that the repo does not configure explicitly).
- The wiki does not contain secret values. Placeholders such as `CHANGE_TO_A_LONG_RANDOM_SECRET` are template text from the `.env.example` files.
