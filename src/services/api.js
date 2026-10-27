const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error {
  constructor(message, status, details = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

/**
 * Format FastAPI/Pydantic validation errors into clean user-facing error text.
 */
function parseErrorMessage(data) {
  if (!data) return 'Request failed';
  const detail = data.detail;
  if (!detail) return data.message || 'Request failed';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((e) => {
        const field = Array.isArray(e?.loc) ? e.loc.filter((part) => part !== 'body').join('.') : '';
        return field ? `${field}: ${e.msg}` : e?.msg;
      })
      .filter(Boolean);
    return messages.join('; ') || 'Validation failed';
  }
  return 'Request failed';
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
        throw new ApiError(parseErrorMessage(data), response.status, data);
      }

      return response.status === 204 ? null : response.json();
    } catch (err) {
      // Retry idempotently on transient network connection drops (up to retries count)
      if (attempt < retries && (err.name === 'TypeError' || err.message === 'Failed to fetch')) {
        await new Promise((res) => setTimeout(res, 500 * Math.pow(2, attempt)));
        return executeRequest(attempt + 1);
      }
      throw err;
    }
  };

  return executeRequest();
}

export const api = {
  // Auth
  register: (data) => request('/auth/register', { method: 'POST', body: data }),
  login: (data) => request('/auth/login', { method: 'POST', body: data }),
  me: (token) => request('/auth/me', { token, retries: 1 }),

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
