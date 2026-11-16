import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api, safe } from '../services/api';
import { InlineError } from './Section';
import { describeNotification } from '../utils/notifications';
import NotificationRow from './NotificationRow';

// How often the badge refreshes while the tab is open and visible.
const POLL_MS = 30_000;
const PANEL_WIDTH = 360;
const GAP = 8;
const SHOWN = 20;

/**
 * The bell in the header. The badge and the list both read `data`, the last answer from the server, so they
 * cannot disagree. The panel hangs under the header, right-aligned to the bell with a caret pointing at it;
 * on phones it becomes a full-width sheet (see .bell-panel in style.css).
 */
export default function NotificationBell() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [data, setData] = useState(null);
  // The last failure to load, or null. While it is set the list says so instead of showing a stale or empty list.
  const [failure, setFailure] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState(null);
  const box = useRef(null);
  const trigger = useRef(null);

  const load = useCallback(async () => {
    const result = await safe(api.notifications(token, SHOWN));
    if (result.aborted) return;
    if (result.ok) {
      setData(result.data);
      setFailure(null);
    } else {
      setFailure(result.error);
    }
  }, [token]);

  useEffect(() => {
    load();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const close = useCallback(() => {
    setOpen(false);
    setConfirmClear(false);
  }, []);

  // Moving to another page closes the panel.
  useEffect(() => {
    close();
  }, [pathname, close]);

  // Work out where the panel goes: 8px under the header, its right edge on the bell's, caret on the bell's middle.
  const measure = useCallback(() => {
    const bell = trigger.current?.getBoundingClientRect();
    const header = document.querySelector('header')?.getBoundingClientRect();
    if (!bell || !header) return;
    const width = Math.min(PANEL_WIDTH, window.innerWidth - 2 * GAP);
    const right = Math.max(GAP, window.innerWidth - bell.right);
    const left = window.innerWidth - right - width;
    const caret = Math.min(Math.max(bell.left + bell.width / 2 - left - 6, 14), width - 26);
    setPlace({ top: header.bottom + GAP, right, caret });
  }, []);

  useLayoutEffect(() => {
    if (!open) return undefined;
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [open, measure]);

  useEffect(() => {
    if (!open) return undefined;
    const outside = (event) => {
      if (!box.current?.contains(event.target)) close();
    };
    const onKey = (event) => {
      if (event.key !== 'Escape') return;
      close();
      trigger.current?.focus();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, close]);

  // Mark it read, go to the related page, close the panel.
  const openItem = async (item, view) => {
    if (!item.read) {
      const result = await safe(api.readNotification(item.id, token));
      if (!result.ok) {
        setActionError(result.error);
        return;
      }
    }
    close();
    load();
    navigate(view.to);
  };

  const remove = async (item) => {
    const result = await safe(api.deleteNotification(item.id, token));
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    setData((current) => ({ unread_count: result.data.unread_count, items: current.items.filter((other) => other.id !== item.id) }));
    setActionError(null);
  };

  const readAll = async () => {
    const result = await safe(api.readAllNotifications(token));
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    setActionError(null);
    await load();
  };

  const clearAll = async () => {
    const result = await safe(api.clearNotifications(token));
    if (result.ok) {
      setData({ unread_count: result.data.unread_count, items: [] });
      setActionError(null);
    } else {
      setActionError(result.error);
    }
    setConfirmClear(false);
  };

  // No answer yet (or only failures) means no badge: a count we do not have is not shown as 0.
  const unread = data ? data.unread_count : null;
  const rows = data ? data.items.map((item) => ({ item, view: describeNotification(item) })).filter(({ view }) => view) : null;
  const groups = rows
    ? [
        ['New', rows.filter(({ item }) => !item.read)],
        ['Earlier', rows.filter(({ item }) => item.read)],
      ].filter(([, list]) => list.length)
    : [];

  const toggle = () => {
    setActionError(null);
    setConfirmClear(false);
    setOpen((current) => !current);
    if (!open) load();
  };

  return (
    <div className="bell" ref={box}>
      <button
        ref={trigger}
        type="button"
        className="bell-trigger"
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={toggle}
      >
        <Bell aria-hidden="true" />
        {unread > 0 && <span className="bell-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && (
        <div
          className="bell-panel"
          role="dialog"
          aria-label="Notifications"
          style={place ? { top: place.top, right: place.right, '--caret-x': `${place.caret}px` } : { visibility: 'hidden' }}
        >
          <div className="bell-head">
            <b>Notifications</b>
            {!failure && data && (
              <span className="bell-head-actions">
                {confirmClear ? (
                  <span className="bell-confirm" role="group" aria-label="Clear all notifications?">
                    Clear all?
                    <button type="button" className="link-button danger" onClick={clearAll}>Yes</button>
                    <button type="button" className="link-button" onClick={() => setConfirmClear(false)}>No</button>
                  </span>
                ) : (
                  <>
                    {unread > 0 && (
                      <button type="button" className="link-button" onClick={readAll}>
                        Mark all read
                      </button>
                    )}
                    {rows.length > 0 && (
                      <button type="button" className="link-button" onClick={() => setConfirmClear(true)}>
                        Clear all
                      </button>
                    )}
                  </>
                )}
              </span>
            )}
          </div>
          <div className="bell-scroll">
            {actionError && <InlineError error={actionError} context="generic" onRetry={() => setActionError(null)} />}
            {failure ? (
              <div className="bell-state">
                <InlineError error={failure} context="notifications" onRetry={load} />
              </div>
            ) : !data ? (
              <p className="bell-state">Loading…</p>
            ) : rows.length ? (
              groups.map(([heading, list]) => (
                <section key={heading} aria-label={heading}>
                  <h4 className="bell-group">{heading}</h4>
                  <ul className="bell-list">
                    {list.map(({ item, view }) => (
                      <NotificationRow key={item.id} item={item} view={view} onOpen={(row) => openItem(row, view)} onDelete={remove} />
                    ))}
                  </ul>
                </section>
              ))
            ) : (
              <div className="bell-state">
                <p><b>You're all caught up.</b></p>
                <p>We'll notify you about enquiries and messages.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
