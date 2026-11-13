const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error {
  constructor(message, status, details = null, fields = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
    // Per-field problems, e.g. { price: 'Input should be a valid integer' }.
    this.fields = fields;
  }
}

const NETWORK_MESSAGE = 'Could not reach InfyExchange. Check your internet connection and try again.';
const SERVER_MESSAGE = 'Something went wrong on our side. Please try again in a moment.';

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

/**
 * Robust HTTP client with centralized bearer token handling,
 * automatic 401 unauthenticated session clearance, and network retry policy.
 */
export async function request(path, { token, body, headers, retries = 0, ...options } = {}) {
  const effectiveToken = token || localStorage.getItem('infy_token');

  const requestHeaders = {
    ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(effectiveToken ? { Authorization: `Bearer ${effectiveToken}` } : {}),
    ...headers,
  };

  const executeRequest = async (attempt = 0) => {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...options,
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
        throw new ApiError(message, response.status, data, fields);
      }

      return response.status === 204 ? null : response.json();
    } catch (err) {
      const offline = err.name === 'TypeError' || err.message === 'Failed to fetch';
      // Retry idempotently on transient network connection drops (up to retries count)
      if (attempt < retries && offline) {
        await new Promise((res) => setTimeout(res, 500 * Math.pow(2, attempt)));
        return executeRequest(attempt + 1);
      }
      if (offline) throw new ApiError(NETWORK_MESSAGE, 0);
      throw err;
    }
  };

  return executeRequest();
}

export const api = {
  // Auth
  register: (data) => request('/auth/register', { method: 'POST', body: data }),
  login: (data) => request('/auth/login', { method: 'POST', body: data }),
  googleLogin: (credential) => request('/auth/google', { method: 'POST', body: { credential } }),
  me: (token) => request('/auth/me', { token, retries: 1 }),

  // Profile
  completeProfile: (body, token) => request('/users/me/complete-profile', { method: 'POST', body, token }),
  updateProfile: (body, token) => request('/users/me', { method: 'PATCH', body, token }),

  // Listings
  listings: (query) => request(`/listings${query ? `?${new URLSearchParams(query)}` : ''}`, { retries: 1 }),
  listing: (id) => request(`/listings/${id}`, { retries: 1 }),
  createListing: (body, token, signal) => request('/listings', { method: 'POST', body, token, signal }),
  myListings: (token) => request('/listings/me', { token, retries: 1 }),
  deleteListing: (id, token) => request(`/listings/${id}`, { method: 'DELETE', token }),

  // Needs
  needs: (query) => request(`/needs${query ? `?${new URLSearchParams(query)}` : ''}`, { retries: 1 }),
  createNeed: (body, token, signal) => request('/needs', { method: 'POST', body, token, signal }),
  myNeeds: (token) => request('/needs/me', { token, retries: 1 }),

  // Interests & Interactions
  createInterest: (id, body, token) => request(`/interests/listing/${id}`, { method: 'POST', body, token }),
  sent: (token) => request('/interests/sent', { token, retries: 1 }),
  received: (token) => request('/interests/received', { token, retries: 1 }),
  accept: (id, token) => request(`/interests/${id}/accept`, { method: 'PATCH', token }),
  reject: (id, token) => request(`/interests/${id}/reject`, { method: 'PATCH', token }),
  contact: (id, token) => request(`/interests/${id}/contact`, { token }),
  summary: (token) => request('/users/me/summary', { token, retries: 1 }),

  // Admin Control Plane
  adminStats: (token) => request('/admin/stats', { token }),
  adminUsers: (query, token) => request(`/admin/users${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminUpdateUser: (id, body, token) => request(`/admin/users/${id}`, { method: 'PATCH', body, token }),
  adminListings: (query, token) => request(`/admin/listings${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminListingStatus: (id, status, token) => request(`/admin/listings/${id}/status?status=${status}`, { method: 'PATCH', token }),
  adminDeleteListing: (id, token) => request(`/admin/listings/${id}`, { method: 'DELETE', token }),
  adminNeeds: (query, token) => request(`/admin/needs${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
  adminDeleteNeed: (id, token) => request(`/admin/needs/${id}`, { method: 'DELETE', token }),
  adminAuditLogs: (query, token) => request(`/admin/audit-logs${query ? `?${new URLSearchParams(query)}` : ''}`, { token }),
};
