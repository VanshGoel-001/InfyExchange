import { useLayoutEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Header } from './Layout';
import { useOnline } from '../hooks/useOnline';
import { abortPendingReads } from '../services/api';
import { NO_ACCESS_MESSAGE, OFFLINE_MESSAGE } from '../utils/messages';

// Leaving a page cancels the reads it still had waiting. (A layout effect, so it runs before the new page starts its own.)
export function RouteWatcher() {
  const { pathname } = useLocation();
  useLayoutEffect(() => {
    abortPendingReads();
  }, [pathname]);
  return null;
}

// A small notice that does not block anything.
export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <p className="offline-banner" role="status">
      {OFFLINE_MESSAGE}
    </p>
  );
}

// Shown when someone is logged in but may not see a page (for example Admin without the admin role).
export function NoAccess() {
  return (
    <>
      <Header />
      <main className="wide">
        <div className="page-status">
          <p role="alert">{NO_ACCESS_MESSAGE}</p>
          <Link className="outline" to="/">Go to home</Link>
        </div>
      </main>
    </>
  );
}
