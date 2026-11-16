// Where to go after logging in. Only a path inside this site is ever allowed: it must start with one "/",
// and may not be protocol-relative ("//host"), contain a backslash, or carry a scheme ("javascript:", "https:").
export function safeNext(value, fallback = '/listings') {
  const path = String(value ?? '');
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return fallback;
  if (/^\/[a-z][a-z0-9+.-]*:/i.test(path)) return fallback;
  if (/[\u0000-\u001f]/.test(path)) return fallback;
  return path;
}

// The page the person is on now, as something safeNext accepts.
export const currentPath = () => `${window.location.pathname}${window.location.search}`;
