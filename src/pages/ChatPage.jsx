import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Ban, Flag, Send } from 'lucide-react';
import { AppShell } from '../components/Layout';
import { Field, FormError, Pill } from '../components/Ui';
import { ContactReveal } from './AccountPages';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';
import { api } from '../services/api';
import {
  CLOSE_DEAL_VERBS,
  INTEREST_STATUSES,
  LISTING_STATUSES,
  ROLES,
  formatDateTime,
  formatPrice,
  hasChat,
  labelOf,
  toneOf,
} from '../utils/labels';
import { LIMITS, validateReport } from '../utils/validate';

// How often the open chat asks for new messages. The tab pauses while hidden.
const POLL_MS = 4000;

function closedReason(chat) {
  if (chat.blocked_by_me) return 'You blocked this person. Unblock them to message again.';
  if (chat.status === 'PENDING') {
    return chat.i_am_owner ? 'Accept this enquiry to start chatting.' : `Waiting for ${chat.other_name} to accept.`;
  }
  if (chat.status === 'REJECTED') return 'This enquiry was declined.';
  if (chat.returned_at) return 'The item was returned, so this chat is closed.';
  if (chat.status === 'CLOSED' && !chat.deal_closed_at) return 'This item is no longer available, so this chat is closed.';
  return 'You cannot send messages in this chat.';
}

function ReportForm({ onSend, onCancel }) {
  const form = useForm({ reason: '' }, validateReport, ['reason']);
  const submit = form.handleSubmit(async (values) => onSend(values.reason.trim()));

  return (
    <form className="chat-report" onSubmit={submit} noValidate>
      <Field label="What went wrong?" error={form.error('reason')} hint={`${form.values.reason.trim().length} / ${LIMITS.report[1]}`}>
        <textarea {...form.bind('reason')} maxLength={LIMITS.report[1]} />
      </Field>
      <FormError>{form.formError}</FormError>
      <div className="button-row">
        <button className="danger compact" disabled={form.busy}>{form.busy ? 'Sending…' : 'Send report'}</button>
        <button type="button" className="outline compact" onClick={onCancel} disabled={form.busy}>Cancel</button>
      </div>
    </form>
  );
}

export default function ChatPage() {
  const { id } = useParams();
  const { token, user } = useAuth();
  const [chat, setChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [pollError, setPollError] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reporting, setReporting] = useState(false);
  const lastId = useRef(0);
  const loaded = useRef(false);
  const list = useRef(null);

  // The chat this screen is showing now. An answer for a chat the person has already left must be dropped,
  // or it puts the wrong name on screen (and the composer would send to a different person).
  const shownId = useRef(id);
  shownId.current = id;

  const poll = useCallback(async () => {
    const { messages: incoming, ...state } = await api.chat(id, lastId.current, token);
    if (shownId.current !== id) return;
    loaded.current = true;
    setChat(state);
    setPollError('');
    if (incoming.length) {
      lastId.current = incoming[incoming.length - 1].id;
      // Merge by id: a message I just sent can also arrive through the next poll.
      setMessages((current) => {
        const seen = new Set(current.map((message) => message.id));
        return [...current, ...incoming.filter((message) => !seen.has(message.id))];
      });
    }
  }, [id, token]);

  useEffect(() => {
    lastId.current = 0;
    loaded.current = false;
    setChat(null);
    setMessages([]);
    setLoadError('');

    const tick = () =>
      poll().catch((err) => {
        if (shownId.current !== id) return;
        // Only the first load is fatal; a hiccup later keeps the conversation on screen.
        if (loaded.current) setPollError(err.message);
        else setLoadError(err.message);
      });

    tick();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') tick();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [poll, id]);

  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [messages.length]);

  // One place for "call the API, say what happened, refresh the screen".
  const act = async (call, done) => {
    setBusy(true);
    setActionError('');
    setNotice('');
    try {
      await call();
      // Refresh first, so the notice never appears next to a screen that still shows the old state.
      await poll();
      if (done) setNotice(done);
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const send = async (event) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setActionError('');
    try {
      await api.sendMessage(id, body, token);
      setDraft('');
      await poll();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSending(false);
    }
  };

  if (loadError) {
    return (
      <AppShell>
        <p role="alert" className="error">{loadError}</p>
        <Link className="primary" to="/activity">Back to enquiries</Link>
      </AppShell>
    );
  }

  if (!chat) {
    return (
      <AppShell>
        <p className="page-status">Loading chat…</p>
      </AppShell>
    );
  }

  const itemOut = chat.listing_status === 'RENTED';
  const canClose = chat.i_am_owner && chat.status === 'ACCEPTED' && chat.listing_status === 'ACTIVE';
  const verb = CLOSE_DEAL_VERBS[chat.listing_type];
  const resultingStatus = chat.listing_type === 'SELL' || chat.listing_type === 'GIVEAWAY' ? 'SOLD' : 'RENTED';

  const closeDeal = () => {
    if (
      !window.confirm(
        `Mark “${chat.listing_title}” as ${verb} ${chat.other_name}? It will show as ${labelOf(LISTING_STATUSES, resultingStatus).toLowerCase()}, ` +
          'and every other open enquiry will be closed and told it is no longer available.'
      )
    ) {
      return;
    }
    act(() => api.closeDeal(id, token), `Deal closed: ${verb.toLowerCase()} ${chat.other_name}.`);
  };

  const toggleBlock = () => {
    if (!chat.blocked_by_me && !window.confirm(`Block ${chat.other_name}? Neither of you will be able to message the other.`)) return;
    act(() => (chat.blocked_by_me ? api.unblockUser(id, token) : api.blockUser(id, token)), chat.blocked_by_me ? 'Unblocked.' : 'Blocked.');
  };

  return (
    <AppShell>
      <Link className="back-link" to="/activity">← Enquiries</Link>

      <section className="panel chat-head">
        <div>
          <h1>
            {chat.other_name}
            {chat.other_role && <small> · {labelOf(ROLES, chat.other_role)}</small>}
          </h1>
          <p>
            <Link to={`/listings/${chat.listing_id}`}>{chat.listing_title}</Link> · {formatPrice(chat.price, chat.price_unit)}
          </p>
          <div className="chat-pills">
            <Pill tone={toneOf(LISTING_STATUSES, chat.listing_status)}>{labelOf(LISTING_STATUSES, chat.listing_status)}</Pill>
            <Pill tone={toneOf(INTEREST_STATUSES, chat.status)}>{labelOf(INTEREST_STATUSES, chat.status)}</Pill>
          </div>
        </div>
        <div className="chat-actions">
          {canClose && (
            <button type="button" className="primary" disabled={busy} onClick={closeDeal}>
              Close deal with {chat.other_name}
            </button>
          )}
          {chat.i_am_owner && itemOut && (
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => window.confirm(`Mark “${chat.listing_title}” as returned? It will be available again.`) && act(() => api.markReturned(chat.listing_id, token), 'Marked as returned. The item is available again.')}
            >
              Mark returned
            </button>
          )}
          {hasChat(chat) && <ContactReveal interestId={chat.interest_id} token={token} />}
        </div>
      </section>

      {notice && <p role="status" className="flash">{notice}</p>}
      {actionError && <p role="alert" className="error">{actionError}</p>}

      {chat.reminder_pending && (
        <div className="chat-banner">
          <p>This chat has been quiet for a while. Is the deal done, or is the item still available?</p>
          <div className="button-row">
            {canClose && (
              <button type="button" className="primary compact" disabled={busy} onClick={closeDeal}>
                Close deal with {chat.other_name}
              </button>
            )}
            <button type="button" className="outline compact" disabled={busy} onClick={() => act(() => api.stillAvailable(id, token), 'Thanks. We will check in again later.')}>
              Still available
            </button>
          </div>
        </div>
      )}

      {!chat.i_am_owner && chat.deal_closed_at && chat.received_confirmed === null && (
        <div className="chat-banner">
          <p>{chat.other_name} closed the deal with you. Did you get it?</p>
          <div className="button-row">
            <button type="button" className="primary compact" disabled={busy} onClick={() => act(() => api.answerReceived(id, true, token))}>Yes</button>
            <button type="button" className="outline compact" disabled={busy} onClick={() => act(() => api.answerReceived(id, false, token))}>No</button>
          </div>
        </div>
      )}

      {chat.received_confirmed !== null && (
        <p className="chat-note">
          {chat.i_am_owner
            ? chat.received_confirmed ? `${chat.other_name} confirmed they got it.` : `${chat.other_name} says they have not got it yet.`
            : chat.received_confirmed ? 'You confirmed you got it.' : 'You said you have not got it yet.'}
        </p>
      )}

      <section className="panel chat-box">
        {pollError && <p role="alert" className="error">Could not refresh: {pollError}</p>}
        <div className="chat-list" ref={list} aria-live="polite">
          {!messages.length && <p className="empty">{chat.can_send ? 'No messages yet. Say hello.' : 'No messages.'}</p>}
          {messages.map((message) => (
            <div key={message.id} className={`msg${message.sender_id === user.id ? ' mine' : ''}`}>
              <p>{message.body}</p>
              <small>{formatDateTime(message.created_at)}</small>
            </div>
          ))}
        </div>

        {chat.can_send ? (
          <form className="chat-composer" onSubmit={send}>
            <textarea
              aria-label="Message"
              value={draft}
              maxLength={LIMITS.chatMessage}
              rows={2}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) send(event);
              }}
            />
            <button className="primary" disabled={sending || !draft.trim()} aria-label="Send message">
              <Send aria-hidden="true" />
            </button>
          </form>
        ) : (
          <p className="chat-closed">{closedReason(chat)}</p>
        )}
      </section>

      <div className="chat-tools">
        <button type="button" className="link-button" onClick={() => setReporting((current) => !current)}>
          <Flag aria-hidden="true" /> Report {chat.other_name}
        </button>
        <button type="button" className="link-button" disabled={busy} onClick={toggleBlock}>
          <Ban aria-hidden="true" /> {chat.blocked_by_me ? 'Unblock' : 'Block'} {chat.other_name}
        </button>
      </div>

      {reporting && (
        <ReportForm
          onCancel={() => setReporting(false)}
          onSend={async (reason) => {
            await api.reportUser(id, reason, token);
            setReporting(false);
            setNotice('Thanks. An admin will look into it.');
          }}
        />
      )}
    </AppShell>
  );
}
