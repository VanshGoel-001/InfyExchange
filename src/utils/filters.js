// Client-side filtering for endpoints without server-side filter support
// (/listings/me, /needs/me). Mirrors the backend query semantics:
// enum fields match exactly, search/location are case-insensitive
// substrings, and price bounds are numeric comparisons.

const EXACT_KEYS = new Set(['category', 'listing_type', 'condition', 'need_type']);

function matchesFilter(item, key, value) {
  const needle = String(value).toLowerCase();

  if (key === 'min_price') return Number(item.price || 0) >= Number(value);
  if (key === 'max_price') return Number(item.price || 0) <= Number(value);

  if (key === 'search') return String(item.title || '').toLowerCase().includes(needle);

  const haystack = String(item[key] ?? '').toLowerCase();
  return EXACT_KEYS.has(key) ? haystack === needle : haystack.includes(needle);
}

export function applyClientFilters(items, filters) {
  return items.filter((item) =>
    Object.entries(filters).every(([key, value]) => matchesFilter(item, key, value))
  );
}
