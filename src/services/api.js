const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error { constructor(message, status) { super(message); this.status=status; } }

// FastAPI validation errors arrive as a structured detail array ({loc, msg, ...});
// surface the validators' own messages instead of stringifying the raw array.
function detailMessage(detail){
  if (!detail) return 'Request failed';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(e => {
      const field = Array.isArray(e?.loc) ? e.loc.filter(part => part !== 'body').join('.') : '';
      return field ? `${field}: ${e.msg}` : e?.msg;
    }).filter(Boolean);
    return messages.join('; ') || 'Request failed';
  }
  return 'Request failed';
}

export async function request(path, {token, body, headers, ...options} = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {...(body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...(token ? {Authorization:`Bearer ${token}`} : {}), ...headers},
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) { const data = await response.json().catch(()=>({})); throw new ApiError(detailMessage(data.detail), response.status); }
  return response.status === 204 ? null : response.json();
}

export const api={
  register: data=>request('/auth/register',{method:'POST',body:data}), login:data=>request('/auth/login',{method:'POST',body:data}), me:token=>request('/auth/me',{token}),
  listings: query=>request(`/listings${query ? `?${new URLSearchParams(query)}` : ''}`), listing:id=>request(`/listings/${id}`), createListing:(body,token)=>request('/listings',{method:'POST',body,token}), myListings:token=>request('/listings/me',{token}), deleteListing:(id,token)=>request(`/listings/${id}`,{method:'DELETE',token}),
  needs: query=>request(`/needs${query ? `?${new URLSearchParams(query)}` : ''}`), createNeed:(body,token)=>request('/needs',{method:'POST',body,token}), myNeeds:token=>request('/needs/me',{token}),
  createInterest:(id,body,token)=>request(`/interests/listing/${id}`,{method:'POST',body,token}), sent:token=>request('/interests/sent',{token}), received:token=>request('/interests/received',{token}), accept:(id,token)=>request(`/interests/${id}/accept`,{method:'PATCH',token}), reject:(id,token)=>request(`/interests/${id}/reject`,{method:'PATCH',token}), summary:token=>request('/users/me/summary',{token}),
};
