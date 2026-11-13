import { useEffect, useRef, useState } from 'react';

// Public, not a secret: the OAuth client ID only says which app is asking. It is baked in at build time.
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

const SCRIPT_SRC = 'https://accounts.google.com/gsi/client';

let scriptPromise;
function loadGoogleScript() {
  scriptPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const script = document.createElement('script');
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      scriptPromise = undefined; // allow a retry on the next mount
      reject(new Error('Could not load Google sign-in.'));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

/**
 * Google's own "Continue with Google" button. Google returns a signed ID token (`credential`);
 * the parent sends it to our API, which verifies it. Renders nothing when no client ID is configured,
 * so the page falls back to email + password.
 */
export default function GoogleButton({ onCredential, onError, text = 'continue_with' }) {
  const box = useRef(null);
  const [ready, setReady] = useState(false);
  // Keep the latest callbacks without re-initialising Google's button on every parent render.
  const handlers = useRef({ onCredential, onError });
  handlers.current = { onCredential, onError };

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return undefined;
    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (cancelled || !box.current) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (response) => handlers.current.onCredential(response.credential),
        });
        window.google.accounts.id.renderButton(box.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text,
          shape: 'rectangular',
          width: Math.min(360, box.current.parentElement?.clientWidth || 360),
        });
        setReady(true);
      })
      .catch((error) => handlers.current.onError?.(error.message));

    return () => {
      cancelled = true;
    };
  }, [text]);

  if (!GOOGLE_CLIENT_ID) return null;
  return <div className="google-slot" ref={box} aria-busy={!ready} />;
}
