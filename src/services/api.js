const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

// What kind of failure it was: offline | network | timeout | server | auth | forbidden | notfound | invalid | conflict | limited | other.
const kindOf = (status) => {
  if (status === 401) return 'auth';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'notfound';
  if (status === 409) return 'conflict';
  if (status === 429) return 'limited';
  if (status === 400 || status === 422) return 'invalid';
  if (status >= 500) return 'server';
  return 'other';
};

export class ApiError extends Error {
  constructor(message, status, details = null, fields = {}, { kind, ref } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
    // Per-field problems, e.g. { price: 'Input should be a valid integer' }.
    this.fields = fields;
    this.kind = kind ?? kindOf(status);
    // The server's request id, for an admin to quote. Normal members are never shown it.
    this.ref = ref ?? null;
  }
}

const NETWORK_MESSAGE = 'Could not reach InfyExchange. Check your internet connection and try again.';
const SERVER_MESSAGE = 'Something went wrong on our side. Please try again in a moment.';
const TIMEOUT_MESSAGE = 'InfyExchange took too long to answer. Check your connection and try again.';
const REQUEST_TIMEOUT_MS = 8_000;
const UPLOAD_TIMEOUT_MS = 120_000;

// The backend answers validation failures with either one "field: message" string or a list of them.
// FastAPI's own shape (a list of { loc, msg } objects) is handled too.
function readValidationItem(item) {
  if (typeof item === 'string') {
    const match = item.match(/^([a-z_][a-z0-9_.]*): (.+)$/i);
    return match ? [match[1], match[2]] : [null, item];
  }
  const field = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== 'body').join('.') : '';
  return [field || null, item?.msg];
}

/** Turn an error response body into user-facing text plus a per-field map. */
function parseError(data, status) {
  const detail = data?.detail;
  // 503 is how the API says "this optional feature is off" (e.g. Google sign-in); its text is meant for people.
  if (status >= 500 && !(status === 503 && typeof detail === 'string')) return { message: SERVER_MESSAGE, fields: {} };
  if (!detail) return { message: data?.message || 'The request could not be completed.', fields: {} };
  if (typeof detail === 'string' && status !== 422) return { message: detail, fields: {} };

  const items = Array.isArray(detail) ? detail : [detail];
  const fields = {};
  const messages = [];
  for (const item of items) {
    const [field, text] = readValidationItem(item);
    if (!text) continue;
    const clean = String(text).replace(/^Value error, /, '');
    if (field && !fields[field]) fields[field] = clean;
    messages.push(field ? `${field}: ${clean}` : clean);
  }
  return { message: messages.join('; ') || 'Please check the details you entered.', fields };
}

// Every GET that is still waiting when the page changes is cancelled, so a slow answer for the page
// someone has left can never fill in (or fail on) the page they are on now.
let pageReads = new AbortController();
export function abortPendingReads() {
  pageReads.abort();
  pageReads = new AbortController();
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The HTTP client: bearer token, an 8 second deadline (longer for photo uploads), and one automatic retry
 * with backoff for GET requests only (never for writes). Failures throw ApiError with a `kind`; most
 * callers use `safe()` below, which never throws.
 */
export async function request(path, { token, body, headers, ...options } = {}) {
  const effectiveToken = token || localStorage.getItem('infy_token');
  const isRead = !options.method || options.method === 'GET';
  const maxRetries = isRead ? 1 : 0;

  const requestHeaders = {
    ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(effectiveToken ? { Authorization: `Bearer ${effectiveToken}` } : {}),
    ...headers,
  };

  const executeRequest = async (attempt = 0) => {
    // Without a deadline, one lost answer leaves a form "busy" forever. A photo upload gets longer.
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, body instanceof FormData ? UPLOAD_TIMEOUT_MS : REQUEST_TIMEOUT_MS);
    // The caller's own cancel (e.g. leaving the posting page) must still cancel the request.
    const onCallerAbort = () => controller.abort();
    if (options.signal?.aborted) controller.abort();
    options.signal?.addEventListener('abort', onCallerAbort, { once: true });
    // Reads also stop when the page changes.
    const readSignal = isRead ? pageReads.signal : null;
    if (readSignal?.aborted) controller.abort();
    readSignal?.addEventListener('abort', onCallerAbort, { once: true });

    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        signal: controller.signal,
        headers: requestHeaders,
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
      });

      if (!response.ok) {
        // Automatically evict expired or revoked tokens on 401
        if (response.status === 401) {
          localStorage.removeItem('infy_token');
          // Dispatch a custom event so React contexts can handle auto-logout gracefully
          window.dispatchEvent(new CustomEvent('auth:expired'));
        }

        const data = await response.json().catch(() => ({}));
        const { message, fields } = parseError(data, response.status);
        const ref = response.headers.get('X-Request-ID') || data?.ref || null;
        const failure = new ApiError(message, response.status, data, fields, { ref });
        // A server fault is worth one more try for a read; everything else is final.
        if (failure.kind === 'server' && attempt < maxRetries) {
          await sleep(600 * 2 ** attempt);
          return executeRequest(attempt + 1);
        }
        throw failure;
      }

      return response.status === 204 ? null : await response.json();
    } catch (err) {
      const unreachable = err.name === 'TypeError' || err.message === 'Failed to fetch';
      // Slow or dropped connection: one more try for a read, after a short wait.
      if ((timedOut || unreachable) && attempt < maxRetries) {
        await sleep(600 * 2 ** attempt);
        return executeRequest(attempt + 1);
      }
      if (timedOut) throw new ApiError(TIMEOUT_MESSAGE, 0, null, {}, { kind: 'timeout' });
      if (unreachable) throw new ApiError(NETWORK_MESSAGE, 0, null, {}, { kind: navigator.onLine === false ? 'offline' : 'network' });
      throw err;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', onCallerAbort);
      readSignal?.removeEventListener('abort', onCallerAbort);
    }
  };

  return executeRequest();
}

/**
 * Wait for an API call and answer { ok, data, error } instead of throwing, so a failed request can never
 * crash the page that made it. `error` is { kind, message, status, ref } (null when ok). A request that was
 * cancelled on purpose (the person left the page) answers { ok: false, aborted: true } and should be ignored.
 */
export async function safe(call) {
  try {
    return { ok: true, data: await call, error: null };
  } catch (err) {
    if (err?.name === 'AbortError') return { ok: false, data: null, error: null, aborted: true };
    return { ok: false, data: null, error: toFailure(err) };
  }
}

// Any thrown value as the plain failure object the UI works with.
export function toFailure(err) {
  if (err instanceof ApiError) {
    return { kind: err.kind, message: err.message, status: err.status, ref: err.ref, fields: err.fields };
  }
  // Not an API failure: a bug in our own code. Keep the detail for the console, show nothing technical.
  console.error('Unexpected error:', err);
  return { kind: 'other', message: '', status: 0, ref: null, fields: {} };
}

// The API serves at most 100 rows a page (20 if no limit is sent), so a person with more
// enquiries, items or requests than that would silently not see the rest. Keep asking until a page comes back short.
const PAGE_SIZE = 100;
const MAX_PAGES = 20;
async function requestAll(path, token) {
  const items = [];
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const batch = await request(`${path}?limit=${PAGE_SIZE}&skip=${page * PAGE_SIZE}`, { token });
    items.push(...batch);
    if (batch.length < PAGE_SIZE) break;
  }
  return items;
}

const withKey = (key) => (key ? { 'Idempotency-Key': key } : undefined);

export const api = {
  // Auth
  register: (data) => request('/auth/register', { method: 'POST', body: data }),
  login: (data) => request('/auth/login', { method: 'POST', body: data }),
  googleLogin: (credential) => request('/auth/google', { method: 'POST', body: { credential } }),
  me: (token) => request('/auth/me', { token }),

  // Profile
  completeProfile: (body, token) => request('/users/me/complete-profile', { method: 'POST', body, token }),
  updateProfile: (body, token) => request('/users/me', { method: 'PATCH', body, token }),

  // Listings
  listings: (query) => request(`/listings${query ? `?${new URLSearchParams(query)}` : ''}`),
  pickupAreas: () => request('/pickup-areas'),
  listing: (id) => request(`/listings/${id}`),
  // `key` is an Idempotency-Key: the same key sent again returns the first result instead of creating a second.
  createListing: (body, token, signal, key) => request('/listings', { method: 'POST', body, token, signal, headers: withKey(key) }),
  myListings: (token) => requestAll('/listings/me', token),
  // `reason` is one of the owner reasons in labels.js (REMOVAL_REASONS).
  deleteListing: (id, token, reason) => request(`/listings/${id}`, { method: 'DELETE', body: reason ? { reason } : undefined, token }),
  // The price is the only thing an owner can change after posting.
  updatePrice: (id, price, token) => request(`/listings/${id}`, { method: 'PUT', body: { price }, token }),
  markReturned: (id, token) => request(`/listings/${id}/mark-returned`, { method: 'POST', token }),

  // Needs
  needs: (query) => request(`/needs${query ? `?${new URLSearchParams(query)}` : ''}`),
  createNeed: (body, token, signal, key) => request('/needs', { method: 'POST', body, token, signal, headers: withKey(key) }),
  myNeeds: (token) => requestAll('/needs/me', token),

  // Interests & Interactions
  createInterest: (id, body, token, key) => request(`/interests/listing/${id}`, { method: 'POST', body, token, headers: withKey(key) }),
  sent: (token) => requestAll('/interests/sent', token),
  received: (token) => requestAll('/interests/received', token),
  accept: (id, token) => request(`/interests/${id}/accept`, { method: 'PATCH', token }),
  reject: (id, token, reply) => request(`/interests/${id}/reject`, { method: 'PATCH', body: reply ? { reply } : undefined, token }),
  closeDeal: (id, token) => request(`/interests/${id}/close-deal`, { method: 'POST', token }),
  stillAvailable: (id, token) => request(`/interests/${id}/still-available`, { method: 'POST', token }),
  answerReceived: (id, received, token) => request(`/interests/${id}/received`, { method: 'POST', body: { received }, token }),
  contact: (id, token) => request(`/interests/${id}/contact`, { token }),

  // Chat on an accepted enquiry
  chat: (id, afterId, token) => request(`/interests/${id}/chat?after_id=${afterId}`, { token }),
  sendMessage: (id, body, token, key) => request(`/interests/${id}/messages`, { method: 'POST', body: { body }, token, headers: withKey(key) }),
  reportUser: (id, reason, token) => request(`/interests/${id}/report`, { method: 'POST', body: { reason }, token }),
  blockUser: (id, token) => request(`/interests/${id}/block`, { method: 'POST', token }),
  unblockUser: (id, token) => request(`/interests/${id}/block`, { method: 'DELETE', token }),

  // Notification bell
  notifications: (token, limit = 20) => request(`/notifications?limit=${limit}`, { token }),
  deleteNotification: (id, token) => request(`/notifications/${id}`, { method: 'DELETE', token }),
  clearNotifications: (token) => request('/notifications', { method: 'DELETE', token }),
  readNotification: (id, token) => request(`/notifications/${id}/read`, { method: 'POST', token }),
  readAllNotifications: (token) => request('/notifications/read-all', { method: 'POST', token }),
  summary: (token) => request('/users/me/summary', { token }),

  // Admin Control Plane
  adminStats: (token) => request('/admin/stats', { token }),
  adminUsers: (query, token) => request(`/admin/users${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminUpdateUser: (id, body, token) => request(`/admin/users/${id}`, { method: 'PATCH', body, token }),
  adminListings: (query, token) => request(`/admin/listings${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminListingStatus: (id, status, token) => request(`/admin/listings/${id}/status?status=${status}`, { method: 'PATCH', token }),
  // An admin removal always carries the reason the owner will be shown.
  adminDeleteListing: (id, reason, token) => request(`/admin/listings/${id}`, { method: 'DELETE', body: { reason }, token }),
  adminNeeds: (query, token) => request(`/admin/needs${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminDeleteNeed: (id, reason, token) => request(`/admin/needs/${id}`, { method: 'DELETE', body: { reason }, token }),
  adminRemovals: (query, token) => request(`/admin/removals${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminPickupAreas: (token) => request('/admin/pickup-areas', { token }),
  adminCreatePickupArea: (body, token) => request('/admin/pickup-areas', { method: 'POST', body, token }),
  adminUpdatePickupArea: (id, body, token) => request(`/admin/pickup-areas/${id}`, { method: 'PATCH', body, token }),
  adminReports: (token) => request('/admin/reports', { token }),
  adminFailedEmails: (token) => request('/admin/failed-emails', { token }),
  adminRetryEmail: (id, token) => request(`/admin/failed-emails/${id}/retry`, { method: 'POST', token }),
  adminDiscardEmail: (id, token) => request(`/admin/failed-emails/${id}`, { method: 'DELETE', token }),
  adminAuditLogs: (query, token) => request(`/admin/audit-logs${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
};
