import { useCallback, useEffect, useRef, useState } from 'react';
import { safe } from '../services/api';

/**
 * Load something from the API and tell the three states apart:
 *   status 'loading' - nothing yet (show a skeleton)
 *   status 'ready'   - real data came back (it may be an empty list: that is "empty", not a failure)
 *   status 'failed'  - the request failed; `error` says how
 * If a reload fails after data was already shown, `data` keeps the last good answer so the page can keep it on
 * screen with a small message instead of blanking. `fetcher` returns a promise from `api`. The newest request
 * wins, and one cancelled because the person left the page is ignored.
 */
export function useLoad(fetcher, deps) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null });
  const newest = useRef(0);
  const latest = useRef(fetcher);
  latest.current = fetcher;

  const reload = useCallback(async () => {
    const mine = ++newest.current;
    setState((current) => (current.status === 'ready' ? current : { status: 'loading', data: current.data, error: null }));
    const result = await safe(latest.current());
    if (mine !== newest.current || result.aborted) return;
    setState((current) =>
      result.ok ? { status: 'ready', data: result.data, error: null } : { status: 'failed', data: current.data, error: result.error }
    );
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    reload();
  }, deps);

  return { ...state, reload };
}
