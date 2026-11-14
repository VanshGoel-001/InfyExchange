import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import { formatDateTime } from '../utils/labels';

// How often the badge refreshes while the tab is open and visible.
const POLL_MS = 30_000;

/** The bell in the header: an unread count, and a list of recent notifications that link to their chat. */
export default function NotificationBell() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState({ unread_count: 0, items: [] });
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const box = useRef(null);

  const load = useCallback(async () => {
    try {
      setData(await api.notifications(token));
      setError('');
    } catch (err) {
      setError(err.message);
    }
  }, [token]);

  useEffect(() => {
    load();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (!box.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const openItem = async (item) => {
    try {
      if (!item.read) await api.readNotification(item.id, token);
    } catch (err) {
      setError(err.message);
      return;
    }
    setOpen(false);
    load();
    if (item.interest_id) navigate(`/chats/${item.interest_id}`);
  };

  const readAll = async () => {
    try {
      await api.readAllNotifications(token);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const unread = data.unread_count;

  return (
    <div className="bell" ref={box}>
      <button
        type="button"
        className="bell-trigger"
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        onClick={() => {
          setOpen((current) => !current);
          if (!open) load();
        }}
      >
        <Bell aria-hidden="true" />
        {unread > 0 && <span className="bell-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && (
        <div className="bell-panel">
          <div className="bell-head">
            <b>Notifications</b>
            {unread > 0 && (
              <button type="button" className="link-button" onClick={readAll}>
                Mark all read
              </button>
            )}
          </div>
          {error && <p role="alert" className="error">{error}</p>}
          {data.items.map((item) => (
            <button
              type="button"
              key={item.id}
              className={`bell-item${item.read ? '' : ' unread'}`}
              onClick={() => openItem(item)}
            >
              <span>{item.message}</span>
              <small>{formatDateTime(item.created_at)}</small>
            </button>
          ))}
          {!data.items.length && !error && <p className="empty">Nothing yet. We will tell you when something happens.</p>}
        </div>
      )}
    </div>
  );
}
