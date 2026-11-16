import { X } from 'lucide-react';
import { formatDateTime, parseTime } from '../utils/labels';
import { relativeTime } from '../utils/notifications';

/**
 * One notification in the bell. The main area opens it; the small × deletes it.
 * `view` comes from describeNotification, so everything shown is plain text built from templates.
 */
export default function NotificationRow({ item, view, onOpen, onDelete }) {
  return (
    <li className={`bell-row${item.read ? '' : ' unread'}`}>
      <button type="button" className={`bell-item${item.read ? '' : ' unread'}`} onClick={() => onOpen(item)}>
        <span className="bell-avatar" aria-hidden="true">
          {view.avatar ?? <view.Icon />}
        </span>
        <span className="bell-body">
          <span className="bell-title">
            {view.title.map((piece, i) => (piece.name ? <b key={i}>{piece.text}</b> : <span key={i}>{piece.text}</span>))}
          </span>
          {view.secondary && <span className="bell-sub">{view.secondary}</span>}
        </span>
        <span className="bell-meta">
          <time dateTime={item.created_at} title={formatDateTime(item.created_at)}>
            {relativeTime(parseTime(item.created_at))}
          </time>
          {!item.read && <span className="bell-dot" role="img" aria-label="Unread" />}
        </span>
      </button>
      <button type="button" className="bell-delete" aria-label="Delete notification" onClick={() => onDelete(item)}>
        <X aria-hidden="true" />
      </button>
    </li>
  );
}
