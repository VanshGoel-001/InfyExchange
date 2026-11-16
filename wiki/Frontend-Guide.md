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
| `/activity` | `ActivityPage` | login required – shown to users as **Enquiries**: enquiries received (accept, one-tap decline with quick replies) and sent, each with an *Open chat* link, unread badge and contact reveal |
| `/chats/:id` | `ChatPage` | login required – the thread for one enquiry: messages (polled every 4 s), **Close deal with [name]**, Mark returned, the "Did you get it?" and 48-hour reminder banners, report and block |
| `/my-listings` | `MyListingsPage` | login required – "My items": view, **edit the price** (the only editable field), **mark returned** for lent-out items, delete |
| `/my-needs` | `MyNeedsPage` | login required – "My requests": read-only list of own needs |
| `/admin` | `AdminPage` | login **and** `is_admin`, else redirected to `/profile`; tabs (one scrollable row): Overview, Members, Listings, Needs, Pickup areas, Reports, Failed emails (Retry / Discard), Admin log |
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

`request(path, {token, body, headers, ...fetchOptions})`:

- Base URL: `import.meta.env.VITE_API_BASE_URL || '/api'`.
- Adds `Content-Type: application/json` except for `FormData` bodies (the browser sets the multipart boundary) and attaches `Authorization: Bearer …` from the `token` option or `localStorage`.
- On a non-2xx response: a `401` removes the stored token and fires `auth:expired`; the body is parsed and thrown as `ApiError(message, status, details, fields)`. The backend reports validation problems as `"field: message"` strings (one, or a list); they are flattened into `message` and also split into a `fields` map so forms can show each one under its field. `5xx` responses become a generic "Something went wrong on our side" message (except `503` with a text `detail`, used for "Google sign-in is off"), and a network failure becomes "Could not reach InfyExchange...".
- **GET requests retry once**, after a short backoff, when the network drops, the deadline passes or the server answers 5xx. **Writes are never retried automatically.**
- **Deadline:** every call is aborted after **8 s** (120 s for `FormData` uploads) and fails as `kind: 'timeout'`, so a lost answer can never leave a form busy forever. A caller's own `signal` still cancels the request.
- **Reads stop when the page changes:** `RouteWatcher` (in `components/Guards.jsx`) calls `abortPendingReads()` on every path change, so a slow answer for the page someone has left can never fill in (or fail on) the one they are on.
- `ApiError` has a `kind` (`offline`, `network`, `timeout`, `server`, `auth`, `forbidden`, `notfound`, `invalid`, `conflict`, `limited`, `other`) and a `ref` (the server's request id, read from `X-Request-ID`).
- **`safe(promise)` never throws.** It answers `{ ok, data, error }` where `error` is `{ kind, message, status, ref, fields }`; a request cancelled on purpose answers `{ ok: false, aborted: true }` and is ignored. `useLoad(fetcher, deps)` builds on it and tells the three states apart: `loading` (skeleton), `ready` (real data, which may be an empty list) and `failed` (`error` set; the last good `data` is kept so the page can stay on screen with one line).
- `utils/messages.js` is the only place failure wording lives (`failureCopy(error, context)`): "Couldn't load listings. Retry", "Unavailable. Retry" (stat cards, whose value shows "—"), "Couldn't post. Details saved. Retry", "Couldn't send. Try again", "Couldn't load. Retry" (bell), "Not sent. Tap to retry" (chat), "Search unavailable. Retry", "Something went wrong. Retry", "Please log in again.", "You're offline.", "No access.". Problems a person can fix (a bad value, a duplicate, "slow down") keep the server's own plain wording. No status codes or log text are ever shown.
- **One failure, one place:** `InlineError` (one line plus one action, in place) and `SectionBoundary` (a render crash shows only inside its own block, with Retry) live in `components/Section.jsx`. Admins also see a small copyable `Ref …`; members never do. A failed submit keeps everything typed (`useForm` exposes `failure` and `resubmit`) and `FormError` shows the line next to the button.
- **Never turn a failure into 0 or an empty list.** `items === null` means "not loaded yet"; an empty array is a real answer. The empty message only shows after a successful load.
- **Session and access:** a `401` sends the person to `/login?next=<page>` (only a path on this site is accepted, see `utils/redirect.js`) with "Please log in again." once; a `403` or an admin page without the role shows "No access."; an unknown listing is the standard "could not be found" message. `OfflineBanner` shows a small non-blocking "You're offline."
- **Paging:** `requestAll()` backs `myListings`, `myNeeds`, `sent` and `received`. The API returns 20 rows unless told otherwise and at most 100, so it asks 100 at a time until a page comes back short (up to 20 pages).

`api` exposes one function per endpoint (auth, listings, needs, interests, summary, admin). Useful gaps to know about: there is no wrapper for `DELETE /needs/{id}` (so users cannot delete their own needs from the UI; the "My requests" page is read-only), and there is no way to respond to a need (the API has no endpoint for it), so the need card is display-only.

## Pages and components

| File | Contents |
| --- | --- |
| `components/Layout.jsx` | `Logo`, `Header` (desktop: nav, auth buttons, **Post** menu, bell, account dropdown; phones: logo, bell and menu button, with one slide-in panel under the header holding Home/Listings/Needs, then the account section with a full-width Post button, then Logout; the page behind is dimmed and locked while it is open), `Footer` (used only on the auth pages; three real quick links), `Sidebar` (account nav), `AppShell` (header + sidebar + content) |
| `components/NotificationBell.jsx`, `NotificationRow.jsx` | The bell. Badge and list both read one server answer (`GET /notifications?limit=20`), so they agree; the badge is hidden at 0. The header ("Notifications", "Mark all read" only when something is unread, "Clear all" with an inline "Clear all? Yes / No") stays fixed while the list scrolls (thin scrollbar). Rows: initials circle (a clock for expired/closed notices), a title of at most two lines with only the name emphasised, one muted line (listing title or a plain-text preview), relative time, a blue dot when unread, and × to delete. Wording is built from structured fields by `utils/notifications.js`; a notification with no usable sender is not shown. Tapping a row marks it read, goes to the chat, enquiries page or listing, and closes the panel; Esc, an outside click or any page change also close it. A failed load shows "Couldn't load notifications" with Retry. The panel is 360px wide, anchored under the header and right-aligned to the bell with a caret; on phones it is a full-width sheet next to the menu button |
| `components/Gallery.jsx` | `Gallery` (detail page photos: fixed 4:3 frame with the whole picture shown, thumbnails, full-screen viewer with arrows, Escape and tap-to-zoom; "no photo" placeholder with the category icon) |
| `components/Cards.jsx` | `ProductCard` (listing tile: fixed 4:3 photo frame, then badge, title held to 2 lines, price, condition, place) and `NeedCard` (display only) |
| `components/Ui.jsx` | `Banner`, `Pill` (badge), `Field` (label + control + hint/error), `PasswordInput`, `FormError`, `Flash` (one-time success note passed via router state), `Toast` (floating confirmation card: icon, title, message, close button and a countdown bar that pauses on hover or focus; passed as `navigate(path, { state: { toast: { title, message } } })`, shown by `Header`, hides itself after 12 s and clears the history entry so a refresh does not repeat it; used after registration to say the welcome email may be in spam, and after Google sign-in to greet the person), `TipBox` |
| `components/GoogleButton.jsx` | Loads Google's script and renders its button; renders nothing without `VITE_GOOGLE_CLIENT_ID` |
| `hooks/useForm.js` | Form state: errors appear after blur or submit, server field errors are mapped to fields and cleared on edit, submit is locked while busy, the first invalid field is focused |
| `components/ErrorBoundary.jsx` | Class `ErrorBoundary` (render-error fallback with reload button) and `SkeletonCard` loading placeholder |
| `pages/AuthPage.jsx` | Login/register form with inline validation, the Google button, and a role dropdown with no pre-selected value |
| `pages/CompleteProfilePage.jsx` | One-time phone, role and joining date after the first Google sign-in |
| `pages/MarketplacePages.jsx` | `Filters` sidebar, `ListingsPage`, `DetailPage` (`Gallery`: swipeable 4:3 photo strip, dots and counter on phones, arrows and thumbnails on larger screens, keyboard arrows, tap to enlarge; on phones the order is photos, badge/title/price, key details, poster and enquiry, description (4 lines, "Read more"); specs, and a side panel that adapts: own item / unavailable / log in / finish profile / enquiry form / sent) |
| `pages/PostingPage.jsx` | One form for both items and requests; shows the price only when it applies; validates with `utils/validate.js`; `AbortController` plus `useForm`'s busy lock prevent double submits; warns on tab close during submission |
| `pages/NeedsPage.jsx` | Need browsing with filters |
| `pages/AccountPages.jsx` | `ProfilePage` (with inline edit of role and joining date), `ActivityPage` (+ `Requests`, `SentRequests`, `ContactReveal`), `MyListingsPage`, `MyNeedsPage` |
| `pages/AdminPage.jsx` | Tabbed admin console: Overview (count cards that open the tab they count, "needs attention" row, latest 5 log entries), Members (compact rows, tap-to-copy phone, confirmation before Make admin / Deactivate), Listings, Needs, Pickup areas, Reports, Failed emails, Admin log |
| `pages/NotFoundPage.jsx`, `pages/HomePage.jsx` | Misc |
| `utils/filters.js` | `applyClientFilters(items, filters)` – mirrors backend semantics for `…/me` lists |
| `utils/labels.js` | **Single source of truth** for enum to text (categories, types, conditions, roles, statuses), plus price and date formatting. Add a value here when the backend gains one |
| `utils/validate.js` | Client-side rules that mirror the backend's limits (`LIMITS`), and `splitServerError` |

### Filtering

- Public lists (`/listings`, `/needs`) send filters to the server (`search`, `category`, `listing_type`, `condition`, `pickup_area_id`, `block_no`, `min_price`, `max_price`, `need_type`) with `limit=100`.
- "Mine" views fetch everything the API returns for `/…/me` (default page size 20) and filter in the browser with `applyClientFilters`: enum fields (`category`, `listing_type`, `condition`, `need_type`) match exactly; `search` is a title substring; `pickup_area_id` and `block_no` match exactly; prices are numeric bounds.
- Filters live in the URL query string on the listings page, so views are shareable and the back button works.

### Contact reveal

`ContactReveal` fetches `/interests/{id}/contact` only when the user clicks **Show contact details**, then shows `mailto:`/`tel:` links. Nothing sensitive is loaded until then, and the server still enforces acceptance and participation.

### Admin console

`AdminPage` loads data per tab, supports search and a status filter (Members, Listings, Needs), shows placeholder rows while loading and a retry button if a tab fails to load, and performs: activate/deactivate user, grant/revoke admin, set listing status, delete listing, delete need, plus read-only audit log. Success/failure messages appear as a banner above the tabs, and the tabs are real buttons (keyboard-reachable). Rights are enforced on the server; the page also redirects non-admins client-side.

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
- **Client validation duplicates the server rules** (lengths, 5 images, 5 MB, MIME types, block 1–100, photo width of at least 600 px). The server is authoritative; keep both in sync when limits change (`MAX_IMAGES_PER_LISTING`, `MAX_IMAGE_SIZE_MB`).
- **Never render user content as HTML.** The app relies on React's default escaping; the CSP does not allow inline scripts, but the JWT sits in `localStorage` so an XSS bug would still expose it.
- Dates are shown with `toLocaleDateString()`; server values are UTC.
- Currency is hard-coded as `₹` (whole numbers).
