# Frontend Guide

The web app is a React 19 single-page application built with Vite 8. Source is in `src/`; everything else at the repository root (`index.html`, `vite.config.js`, `public/`, `package.json`) is build tooling.

## Tech stack

| Package | Version range | Purpose |
| --- | --- | --- |
| `react`, `react-dom` | ^19.3 | UI |
| `react-router-dom` | ^7.18 | Client-side routing (`BrowserRouter`) |
| `vite`, `@vitejs/plugin-react` | ^8.3 / ^6.1 | Dev server and bundler |
| `lucide-react` | ^1.48 | Icons |
| `@neon/config`, `@neon/env` | ^1.14 / ^2.1 | Used by the root `neon.ts` Neon project config, not by the UI |

There is no TypeScript, state-management library, CSS framework, linter or test runner configured for the frontend. Styling is one global stylesheet, `src/style.css` (~43 KB).

## Entry points

- `index.html` → `src/main.jsx` → renders `<App/>` and imports `style.css`.
- `src/app/App.jsx` composes `ErrorBoundary → AuthProvider → BrowserRouter → Routes` and defines the `Protected` route guard.

## Routes

| Path | Component (file) | Access |
| --- | --- | --- |
| `/` | `HomePage` | public – hero search, category tiles, 4 latest items, "post a request" CTA |
| `/login` | `AuthPage` | public |
| `/register` | `AuthPage register` | public |
| `/complete-profile` | `CompleteProfilePage` | login required; the only protected page an incomplete (Google-created) profile may open |
| `/listings` | `ListingsPage` (`MarketplacePages.jsx`) | public – filters, grid; `?scope=mine` shows own listings |
| `/listings/new` | `PostingPage` | login required |
| `/listings/:id` | `DetailPage` (`MarketplacePages.jsx`) | public view; login and a complete profile needed to send an enquiry |
| `/needs` | `NeedsPage` | public; `?scope=mine` for own |
| `/needs/new` | `PostingPage need` | login required |
| `/profile` | `ProfilePage` (`AccountPages.jsx`) | login required |
| `/activity` | `ActivityPage` | login required – shown to users as **Enquiries**: enquiries received (accept/decline, contact reveal) and sent |
| `/my-listings` | `MyListingsPage` | login required – "My items": view/delete own listings |
| `/my-needs` | `MyNeedsPage` | login required – "My requests": read-only list of own needs |
| `/admin` | `AdminPage` | login **and** `is_admin`, else redirected to `/profile` |
| `*` | `NotFoundPage` | public |

`Protected` waits for the auth bootstrap (`loading`), redirects anonymous users to `/login`, sends users whose `profile_complete` is false to `/complete-profile` (unless `allowIncomplete`), and redirects non-admins away from `adminOnly` routes. This is a UX convenience only – every protected API route re-checks on the server.

## Authentication state (`context/AuthContext.jsx`)

- State: `token` (initialised from `localStorage['infy_token']`), `user`, `loading`.
- On mount / token change: if a token exists, `api.me(token)` loads the profile; failure clears the token.
- `login(credentials)`: `POST /auth/login`, stores the token, then loads the profile and returns it.
- `logout()`: removes the token and user (client-side only; the JWT remains valid until it expires).
- Listens for the window event **`auth:expired`**, which `api.js` dispatches on any `401`, to clear state globally.
- `loginWithGoogle(credential)`: `POST /auth/google` with the ID token Google's button returned, then the same token and profile steps as `login`.
- Exposed through `useAuth()`: `{token, user, loading, login, loginWithGoogle, logout, setUser}`.

The registration form calls `api.register(...)` and immediately `login(...)` with the same credentials, then navigates to `/listings`. After a Google sign-in the app goes to `/complete-profile` when `user.profile_complete` is false, otherwise to `/listings`.

### Vocabulary

Screens use plain words, never API codes: a *need* is a **request** ("Post a request", "My requests"), an *interest* is an **enquiry**, a *listing* is an **item**. All value-to-text mapping lives in `utils/labels.js`.

## API client (`services/api.js`)

`request(path, {token, body, headers, retries, ...fetchOptions})`:

- Base URL: `import.meta.env.VITE_API_BASE_URL || '/api'`.
- Adds `Content-Type: application/json` except for `FormData` bodies (the browser sets the multipart boundary) and attaches `Authorization: Bearer …` from the `token` option or `localStorage`.
- On a non-2xx response: a `401` removes the stored token and fires `auth:expired`; the body is parsed and thrown as `ApiError(message, status, details, fields)`. The backend reports validation problems as `"field: message"` strings (one, or a list); they are flattened into `message` and also split into a `fields` map so forms can show each one under its field. `5xx` responses become a generic "Something went wrong on our side" message (except `503` with a text `detail`, used for "Google sign-in is off"), and a network failure becomes "Could not reach InfyExchange...".
- `retries` (used for idempotent GETs, value 1) retries only network-level `TypeError`/"Failed to fetch" failures with exponential backoff (500 ms × 2^attempt). HTTP errors are never retried.

`api` exposes one function per endpoint (auth, listings, needs, interests, summary, admin). Useful gaps to know about: there is no wrapper for `PUT /listings/{id}` or `DELETE /needs/{id}` (so users cannot edit listings or delete their own needs from the UI; the "My requests" page is read-only), and there is no way to respond to a need (the API has no endpoint for it), so the need card is display-only.

## Pages and components

| File | Contents |
| --- | --- |
| `components/Layout.jsx` | `Logo`, `Header` (nav, auth buttons, **Post** menu, account dropdown, mobile menu, admin link), `Footer` (used only on the auth pages; three real quick links), `Sidebar` (account nav), `AppShell` (header + sidebar + content) |
| `components/Cards.jsx` | `ProductCard` (listing tile with type badge, price, condition, location) and `NeedCard` (display only) |
| `components/Ui.jsx` | `Banner`, `Pill` (badge), `Field` (label + control + hint/error), `PasswordInput`, `FormError`, `Flash` (one-time success note passed via router state), `TipBox` |
| `components/GoogleButton.jsx` | Loads Google's script and renders its button; renders nothing without `VITE_GOOGLE_CLIENT_ID` |
| `hooks/useForm.js` | Form state: errors appear after blur or submit, server field errors are mapped to fields and cleared on edit, submit is locked while busy, the first invalid field is focused |
| `components/ErrorBoundary.jsx` | Class `ErrorBoundary` (render-error fallback with reload button) and `SkeletonCard` loading placeholder |
| `pages/AuthPage.jsx` | Login/register form with inline validation, the Google button, and a role dropdown with no pre-selected value |
| `pages/CompleteProfilePage.jsx` | One-time phone, role and joining date after the first Google sign-in |
| `pages/MarketplacePages.jsx` | `Filters` sidebar, `ListingsPage`, `DetailPage` (first image only – extra uploaded images are stored but not shown –, specs, and a side panel that adapts: own item / unavailable / log in / finish profile / enquiry form / sent) |
| `pages/PostingPage.jsx` | One form for both items and requests; shows the price only when it applies; validates with `utils/validate.js`; `AbortController` plus `useForm`'s busy lock prevent double submits; warns on tab close during submission |
| `pages/NeedsPage.jsx` | Need browsing with filters |
| `pages/AccountPages.jsx` | `ProfilePage` (with inline edit of role and joining date), `ActivityPage` (+ `Requests`, `SentRequests`, `ContactReveal`), `MyListingsPage`, `MyNeedsPage` |
| `pages/AdminPage.jsx` | Tabbed admin console: Overview, Members, Items, Requests, Admin log |
| `pages/NotFoundPage.jsx`, `pages/HomePage.jsx` | Misc |
| `utils/filters.js` | `applyClientFilters(items, filters)` – mirrors backend semantics for `…/me` lists |
| `utils/labels.js` | **Single source of truth** for enum to text (categories, types, conditions, roles, statuses), plus price and date formatting. Add a value here when the backend gains one |
| `utils/validate.js` | Client-side rules that mirror the backend's limits (`LIMITS`), and `splitServerError` |

### Filtering

- Public lists (`/listings`, `/needs`) send filters to the server (`search`, `category`, `listing_type`, `condition`, `location`, `min_price`, `max_price`, `need_type`) with `limit=100`.
- "Mine" views fetch everything the API returns for `/…/me` (default page size 20) and filter in the browser with `applyClientFilters`: enum fields (`category`, `listing_type`, `condition`, `need_type`) match exactly; `search` is a title substring; `location` a substring; prices are numeric bounds.
- Filters live in the URL query string on the listings page, so views are shareable and the back button works.

### Contact reveal

`ContactReveal` fetches `/interests/{id}/contact` only when the user clicks **Show contact details**, then shows `mailto:`/`tel:` links. Nothing sensitive is loaded until then, and the server still enforces acceptance and participation.

### Admin console

`AdminPage` loads data per tab, supports search, and performs: activate/deactivate user, grant/revoke admin, set listing status, delete listing, delete need, plus read-only audit log. Success/failure messages appear as a banner above the tabs, and the tabs are real buttons (keyboard-reachable). Rights are enforced on the server; the page also redirects non-admins client-side.

## Build and configuration

### Scripts

| Command | Effect |
| --- | --- |
| `npm run dev` | `vite --host 127.0.0.1` |
| `npm run build` | `vite build` → `dist/` |
| `npm run preview` | Serve `dist/` locally |

### Dev proxy

`server.proxy: { '/api': 'http://127.0.0.1:8000' }`.

### Build-time API URL validation

`vite.config.js` reads `VITE_API_BASE_URL` (from `.env*` files or the process environment – dashboard/CI values win). In **production mode only** it:

- warns if unset (the app will call `/api` on its own origin),
- throws if the value ends with `/`,
- throws if it does not end with `/api`.

The Pages workflow adds a stricter regex check (`^https://[^/]+/api$`). The value is inlined at build time, so changing it requires a new build and deploy.

### Generated `dist/_headers` (Cloudflare Pages)

The `infyexchange:spa-headers` plugin (build only) writes `_headers` after bundling:

- All routes: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` disabling camera, microphone, geolocation, payment.
- A CSP that allows `'self'` scripts; styles from `'self'` and Google Fonts; fonts from `fonts.gstatic.com`; images from `'self'`, `data:` and `https://res.cloudinary.com`; `connect-src 'self'` plus the **origin of the configured API URL**; `frame-ancestors 'none'`, `object-src 'none'`, `base-uri`/`form-action 'self'`, and `upgrade-insecure-requests` when the API is HTTPS.
- It is emitted as **`Content-Security-Policy-Report-Only`** while `CSP_ENFORCE = false` in `vite.config.js`; flip the constant to enforce after a clean burn-in ([Security](Security.md#browser-side-controls-spa)).
- `/assets/*`: `Cache-Control: public, max-age=31536000, immutable`; `/index.html`: `no-cache`.
- HSTS is present only as a commented-out template.

### `public/_redirects`

`/*  /index.html  200` – the SPA fallback so deep links such as `/listings/12` or `/admin` reach React Router instead of a Pages 404.

## Conventions and pitfalls

- **Formatting is mixed.** `App.jsx`, `AuthContext.jsx`, `Cards.jsx`, `Ui.jsx` and `HomePage.jsx` are written as dense, minified-style one-liners; `Layout.jsx`, `PostingPage.jsx`, `MarketplacePages.jsx`, `AdminPage.jsx` and `api.js` are conventionally formatted. When you touch a dense file, consider reformatting it in the same commit to keep diffs reviewable.
- **Enum strings are duplicated** in several pages (`CATEGORIES`, listing types, conditions). If the backend enums change, search `src/` for the old values.
- **Client validation duplicates the server rules** (lengths, 5 images, 5 MB, MIME types). The server is authoritative; keep both in sync when limits change (`MAX_IMAGES_PER_LISTING`, `MAX_IMAGE_SIZE_MB`).
- **Never render user content as HTML.** The app relies on React's default escaping; the CSP does not allow inline scripts, but the JWT sits in `localStorage` so an XSS bug would still expose it.
- Dates are shown with `toLocaleDateString()`; server values are UTC.
- Currency is hard-coded as `₹` (whole numbers).
