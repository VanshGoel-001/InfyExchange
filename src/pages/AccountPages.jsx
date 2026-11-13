import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Inbox, Megaphone, Package, Pencil, Send } from 'lucide-react';
import { AppShell } from '../components/Layout';
import { Banner, Field, Flash, FormError, Pill } from '../components/Ui';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';
import { NeedCard, ProductCard } from '../components/Cards';
import { SkeletonCard } from '../components/ErrorBoundary';
import {
  INTEREST_STATUSES,
  LISTING_STATUSES,
  ROLES,
  daysLeft,
  formatDate,
  initials,
  labelOf,
  toneOf,
} from '../utils/labels';
import { todayISO, validateProfileEdit } from '../utils/validate';

function EditProfileForm({ user, token, onDone }) {
  const { setUser } = useAuth();
  const form = useForm({ role: user.role || '', joining_date: user.joining_date || '' }, validateProfileEdit, ['role', 'joining_date']);
  const { bind, error } = form;

  const save = form.handleSubmit(async (values) => {
    const updated = await api.updateProfile({ role: values.role, joining_date: values.joining_date }, token);
    setUser(updated);
    onDone('Your profile has been updated.');
  });

  return (
    <form className="edit-profile" onSubmit={save} noValidate>
      <Field label="Your role" required error={error('role')}>
        <select {...bind('role')}>
          <option value="" disabled>Choose your role</option>
          {ROLES.map((role) => (
            <option key={role.value} value={role.value}>{role.option}</option>
          ))}
        </select>
      </Field>
      <Field label="Date you joined Infosys" required error={error('joining_date')}>
        <input {...bind('joining_date')} type="date" max={todayISO()} />
      </Field>
      <FormError>{form.formError}</FormError>
      <div className="button-row">
        <button className="primary" disabled={form.busy} aria-busy={form.busy}>{form.busy ? 'Saving…' : 'Save changes'}</button>
        <button type="button" className="outline" onClick={() => onDone('')} disabled={form.busy}>Cancel</button>
      </div>
    </form>
  );
}

export function ProfilePage() {
  const { token, user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState('');

  useEffect(() => {
    if (!token) return;
    api.summary(token).then(setSummary).catch((e) => setError(e.message));
  }, [token]);

  const stats = [
    [Package, summary?.my_listings_count, 'Items I posted', '/my-listings'],
    [Megaphone, summary?.my_needs_count, 'Requests I posted', '/my-needs'],
    [Send, summary?.my_interests_count, 'Enquiries I sent', '/activity'],
    [Inbox, summary?.requests_received_count, 'Enquiries I received', '/activity', summary?.pending_requests_received_count],
  ];

  return (
    <AppShell>
      <Banner title="My profile" subtitle="Your details and a quick look at what you have going on." />
      <Flash />

      <div className="dashboard-grid profile-dashboard">
        <section>
          <div className="panel personal">
            <h2>
              Your details
              {!editing && (
                <button type="button" className="link-button" onClick={() => { setSaved(''); setEditing(true); }}>
                  <Pencil aria-hidden="true" /> Edit
                </button>
              )}
            </h2>
            {saved && <p role="status" className="flash">{saved}</p>}
            <div className="personal-content">
              <div className="large-avatar">{initials(user.name)}</div>
              {editing ? (
                <EditProfileForm
                  user={user}
                  token={token}
                  onDone={(message) => {
                    setSaved(message);
                    setEditing(false);
                  }}
                />
              ) : (
                <>
                  <div>
                    <small>Name</small>
                    <p>{user.name}</p>
                    <small>Email</small>
                    <p>{user.email}</p>
                    <small>Phone</small>
                    <p>{user.phone}</p>
                  </div>
                  <div>
                    <small>Role</small>
                    <p>{labelOf(ROLES, user.role)}</p>
                    <small>Joined Infosys</small>
                    <p>{formatDate(user.joining_date)}</p>
                  </div>
                </>
              )}
            </div>
            {!editing && <p className="form-lead">You can change your role and joining date. Name, email and phone are fixed.</p>}
          </div>
        </section>

        <section>
          <div className="panel summary">
            <h2>At a glance</h2>
            <div>
              {stats.map(([Icon, count, name, to, waiting]) => (
                <Link className="stat" to={to} key={name}>
                  <Icon aria-hidden="true" />
                  <b>
                    {summary ? count : '—'}
                    <small>{name}</small>
                    {waiting > 0 && <small className="waiting">{waiting} waiting for your reply</small>}
                  </b>
                </Link>
              ))}
            </div>
            {error && <p className="error">{error}</p>}
          </div>

          <div className="panel quick">
            <h2>Quick actions</h2>
            <Link className="outline" to="/listings/new">Post an item</Link>
            <Link className="outline" to="/needs/new">Post a request</Link>
            <Link className="outline" to="/activity">Enquiries</Link>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

export function ActivityPage() {
  const { token } = useAuth();
  const [data, setData] = useState({ sent: [], received: [] });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    Promise.all([api.sent(token), api.received(token)])
      .then(([sent, received]) => setData({ sent, received }))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (token) load();
  }, [token]);

  const respond = async (item, action) => {
    if (
      action === 'accept' &&
      !window.confirm(`Accept ${item.interested_user_name}'s enquiry? You will both be able to see each other's phone and email.`)
    ) {
      return;
    }
    setBusy(item.id);
    setError('');
    setNotice('');
    try {
      await api[action](item.id, token);
      setNotice(action === 'accept' ? 'Enquiry accepted. You can now see each other’s contact details.' : 'Enquiry declined.');
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <AppShell>
      <Banner
        title="Enquiries"
        subtitle="People who asked about your items, and the items you asked about."
        kind="activity"
      />
      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p role="status" className="flash">{notice}</p>}

      <div className="lower-tables">
        <Requests items={data.received} loading={loading} onRespond={respond} busy={busy} token={token} />
        <SentRequests items={data.sent} loading={loading} token={token} />
      </div>
    </AppShell>
  );
}

export function MyListingsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api
      .myListings(token)
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (token) load();
  }, [token]);

  const remove = async (item) => {
    if (!window.confirm(`Delete “${item.title}”? This cannot be undone.`)) return;
    setBusy(item.id);
    setError('');
    try {
      await api.deleteListing(item.id, token);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <AppShell>
      <Banner title="My items" subtitle="Everything you have posted for the community." />
      <Flash />
      <div className="personal-page-head">
        <p>{loading ? 'Loading…' : `${items.length} ${items.length === 1 ? 'item' : 'items'}`}</p>
        <Link className="primary" to="/listings/new">Post an item</Link>
      </div>
      {error && <p role="alert" className="error">{error}</p>}

      {loading ? (
        <div className="my-items-grid">
          {[...Array(3)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <section className="my-items-grid">
          {items.map((item, index) => (
            <article className="my-item" key={item.id}>
              <ProductCard item={item} i={index} />
              <div className="my-item-status">
                <Pill tone={toneOf(LISTING_STATUSES, item.status)}>{labelOf(LISTING_STATUSES, item.status)}</Pill>
                {item.status === 'ACTIVE' && <small>{daysLeft(item.expires_at)}</small>}
              </div>
              <div className="my-item-actions">
                <Link className="outline" to={`/listings/${item.id}`}>View</Link>
                <button className="danger" disabled={busy === item.id} onClick={() => remove(item)}>
                  {busy === item.id ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </article>
          ))}
        </section>
      )}

      {!loading && !items.length && !error && (
        <section className="panel empty-state">
          <h2>You have not posted anything yet</h2>
          <p>Post an item and other trainees can find it.</p>
          <Link className="primary" to="/listings/new">Post an item</Link>
        </section>
      )}
    </AppShell>
  );
}

export function MyNeedsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    api
      .myNeeds(token)
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <AppShell>
      <Banner title="My requests" subtitle="Things you have asked the community for." kind="need" />
      <Flash />
      <div className="personal-page-head">
        <p>{loading ? 'Loading…' : `${items.length} ${items.length === 1 ? 'request' : 'requests'}`}</p>
        <Link className="primary" to="/needs/new">Post a request</Link>
      </div>
      {error && <p role="alert" className="error">{error}</p>}

      <section className="my-items-grid my-needs-grid">
        {items.map((item, index) => (
          <article className="my-item" key={item.id}>
            <NeedCard item={item} i={index} />
          </article>
        ))}
      </section>

      {!loading && !items.length && !error && (
        <section className="panel empty-state">
          <h2>You have not asked for anything yet</h2>
          <p>Post a request and let the community know what you are looking for.</p>
          <Link className="primary" to="/needs/new">Post a request</Link>
        </section>
      )}
    </AppShell>
  );
}

function Requests({ items, loading, onRespond, busy, token }) {
  return (
    <section className="panel request-panel">
      <h2>
        Enquiries about my items <small>({items.length})</small>
      </h2>
      {items.map((item) => (
        <div className="request" key={item.id}>
          <div className="request-main">
            <b>{item.interested_user_name}{item.interested_user_role && <small> · {labelOf(ROLES, item.interested_user_role)}</small>}</b>
            <Link to={`/listings/${item.listing_id}`}>{item.listing_title}</Link>
            <p>{item.message ? `“${item.message}”` : 'No message'}</p>
            <small>{formatDate(item.created_at)}</small>
          </div>
          <div className="request-side">
            <Pill tone={toneOf(INTEREST_STATUSES, item.status)}>{labelOf(INTEREST_STATUSES, item.status)}</Pill>
            {item.status === 'PENDING' && (
              <div className="button-row">
                <button className="primary compact" disabled={busy === item.id} onClick={() => onRespond(item, 'accept')}>
                  Accept
                </button>
                <button className="danger compact" disabled={busy === item.id} onClick={() => onRespond(item, 'reject')}>
                  Decline
                </button>
              </div>
            )}
            {item.status === 'ACCEPTED' && <ContactReveal interestId={item.id} token={token} />}
          </div>
        </div>
      ))}
      {!loading && !items.length && <p className="empty">No one has enquired about your items yet.</p>}
    </section>
  );
}

function SentRequests({ items, loading, token }) {
  return (
    <section className="panel request-panel">
      <h2>
        Items I asked about <small>({items.length})</small>
      </h2>
      {items.map((item) => (
        <div className="request" key={item.id}>
          <div className="request-main">
            <b>
              <Link to={`/listings/${item.listing_id}`}>{item.listing_title}</Link>
            </b>
            <p>{item.message ? `“${item.message}”` : 'No message'}</p>
            <small>{formatDate(item.created_at)}</small>
          </div>
          <div className="request-side">
            <Pill tone={toneOf(INTEREST_STATUSES, item.status)}>{labelOf(INTEREST_STATUSES, item.status)}</Pill>
            {item.status === 'ACCEPTED' && <ContactReveal interestId={item.id} token={token} />}
          </div>
        </div>
      ))}
      {!loading && !items.length && (
        <p className="empty">
          You have not enquired about any items yet. <Link to="/listings">Browse items</Link>
        </p>
      )}
    </section>
  );
}

/**
 * Reveals the other person's contact details after a request is accepted.
 * Nothing is fetched until the click, so details are not loaded for every row.
 * The server still checks that the request is accepted and that you are one of the two people.
 */
function ContactReveal({ interestId, token }) {
  const [state, setState] = useState('idle'); // idle | loading | revealed | error
  const [contact, setContact] = useState(null);
  const [error, setError] = useState('');

  const reveal = async () => {
    setState('loading');
    setError('');
    try {
      setContact(await api.contact(interestId, token));
      setState('revealed');
    } catch (e) {
      setError(e.message || 'Could not load contact details.');
      setState('error');
    }
  };

  if (state === 'revealed' && contact) {
    return (
      <span className="contact-card">
        <b>{contact.name}</b>
        <a href={`mailto:${contact.email}`}>{contact.email}</a>
        <a href={`tel:${contact.phone}`}>{contact.phone}</a>
      </span>
    );
  }

  return (
    <span className="contact-reveal">
      <button className="outline compact" disabled={state === 'loading'} onClick={reveal}>
        {state === 'loading' ? 'Loading…' : 'Show contact details'}
      </button>
      {state === 'error' && <small className="field-error" role="alert">{error}</small>}
    </span>
  );
}
