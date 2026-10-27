import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/Layout';
import { Banner } from '../components/Ui';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { NeedCard, ProductCard } from '../components/Cards';
import { SkeletonCard } from '../components/ErrorBoundary';

const fmt = (value) => String(value || '').replaceAll('_', ' ');
const price = (item) =>
  item.price > 0 ? `₹${item.price}${item.price_unit ? `/${item.price_unit}` : ''}` : 'Free';

export function ProfilePage() {
  const { token, user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    api.summary(token).then(setSummary).catch((e) => setError(e.message));
  }, [token]);

  const cards = [
    ['◇', summary?.my_listings_count, 'My Listings'],
    ['♡', summary?.my_interests_count, 'My Interests'],
    ['⚑', summary?.my_needs_count, 'My Needs'],
    ['▢', summary?.requests_received_count, 'Requests Received'],
  ];

  return (
    <AppShell>
      <Banner title="My Profile" subtitle="Manage your information and see your activity on InfyExchange." />

      <div className="dashboard-grid profile-dashboard">
        <section>
          <div className="panel personal">
            <h2>♙ Personal Information</h2>
            <div className="personal-content">
              <div className="large-avatar">{user.name.slice(0, 2).toUpperCase()}</div>
              <div>
                <small>Full Name</small>
                <p>{user.name}</p>
                <small>Email</small>
                <p>{user.email}</p>
                <small>Phone Number</small>
                <p>{user.phone}</p>
              </div>
              <div>
                <small>Role</small>
                <p>{user.role}</p>
                <small>Joining Date</small>
                <p>{user.joining_date}</p>
              </div>
            </div>
          </div>
        </section>

        <section>
          <div className="panel summary">
            <h2>▥ My Activity Summary</h2>
            <div>
              {cards.map((x) => (
                <article key={x[2]}>
                  <span>{x[0]}</span>
                  <b>
                    {summary ? x[1] : '—'}
                    <small>{x[2]}</small>
                  </b>
                </article>
              ))}
            </div>
            {error && <p className="error">{error}</p>}
          </div>

          <div className="panel quick">
            <h2>ϟ Quick Actions</h2>
            <Link className="outline" to="/listings/new">
              ＋ Post a Listing
            </Link>
            <Link className="outline" to="/needs/new">
              ＋ Post a Need
            </Link>
            <Link className="outline" to="/activity">
              View My Activity
            </Link>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

export function ActivityPage() {
  const { token } = useAuth();
  const [data, setData] = useState({ listings: [], needs: [], sent: [], received: [] });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    Promise.all([api.myListings(token), api.myNeeds(token), api.sent(token), api.received(token)])
      .then(([listings, needs, sent, received]) => setData({ listings, needs, sent, received }))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (token) load();
  }, [token]);

  const respond = async (id, action) => {
    setBusy(id);
    try {
      await api[action](id, token);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this listing?')) return;
    setBusy(id);
    try {
      await api.deleteListing(id, token);
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
        title="My Activity"
        subtitle="Manage your listings, interests and requests all in one place."
        kind="activity"
      />
      {error && <p className="error">{error}</p>}

      <section className="panel table">
        <h2>
          My Listings <small>({data.listings.length})</small>
          <Link className="primary" to="/listings/new">
            ＋ Post New Listing
          </Link>
        </h2>
        <div className="table-head">
          Item <span>Type</span>
          <span>Price</span>
          <span>Status</span>
          <span>Posted On</span>
          <span>Expires In</span>
          <span>Actions</span>
        </div>

        {data.listings.map((item) => (
          <div className="table-row" key={item.id}>
            <div>
              <i>{item.image_url ? <img src={item.image_url} alt="" /> : '▧'}</i>
              <b>
                {item.title}
                <small>
                  {fmt(item.condition)} · {item.location}
                </small>
              </b>
            </div>
            <span>
              <label className="blue">{fmt(item.listing_type)}</label>
            </span>
            <b>{price(item)}</b>
            <span>
              <label className="status">{fmt(item.status)}</label>
            </span>
            <small>{new Date(item.created_at).toLocaleDateString()}</small>
            <small>{new Date(item.expires_at).toLocaleDateString()}</small>
            <span>
              <button className="danger" disabled={busy === item.id} onClick={() => remove(item.id)}>
                {busy === item.id ? 'Deleting…' : 'Delete'}
              </button>
            </span>
          </div>
        ))}
        {!data.listings.length && !loading && (
          <p className="empty">You have not posted any listings.</p>
        )}
      </section>

      <div className="lower-tables">
        <ActivityList title={`My Needs (${data.needs.length})`} items={data.needs} kind="need" />
        <ActivityList title={`My Interests (${data.sent.length})`} items={data.sent} kind="sent" token={token} />
        <Requests items={data.received} onRespond={respond} busy={busy} token={token} />
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

  const remove = async (id) => {
    if (!window.confirm('Delete this listing?')) return;
    setBusy(id);
    try {
      await api.deleteListing(id, token);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <AppShell>
      <Banner title="My Listings" subtitle="Manage the items you have shared with the InfyExchange community." />
      <div className="personal-page-head">
        <p>{items.length} active {items.length === 1 ? 'listing' : 'listings'}</p>
        <Link className="primary" to="/listings/new">
          ＋ Post a Listing
        </Link>
      </div>
      {error && <p className="error">{error}</p>}

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
              <div className="my-item-actions">
                <Link className="outline" to={`/listings/${item.id}`}>
                  View listing
                </Link>
                <button className="danger" disabled={busy === item.id} onClick={() => remove(item.id)}>
                  {busy === item.id ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </article>
          ))}
        </section>
      )}

      {!loading && !items.length && (
        <section className="panel empty-state">
          <h2>No listings yet</h2>
          <p>Post an item to let fellow trainees discover it.</p>
          <Link className="primary" to="/listings/new">
            ＋ Post a Listing
          </Link>
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
      <Banner title="My Needs" subtitle="Review requests you have posted for the InfyExchange community." kind="need" />
      <div className="personal-page-head">
        <p>{items.length} active {items.length === 1 ? 'need' : 'needs'}</p>
        <Link className="primary" to="/needs/new">
          ＋ Post a Need
        </Link>
      </div>
      {error && <p className="error">{error}</p>}

      <section className="my-items-grid my-needs-grid">
        {items.map((item, index) => (
          <article className="my-item" key={item.id}>
            <NeedCard item={item} i={index} />
          </article>
        ))}
      </section>

      {!loading && !items.length && (
        <section className="panel empty-state">
          <h2>No needs yet</h2>
          <p>Post a request and let the community know how it can help.</p>
          <Link className="primary" to="/needs/new">
            ＋ Post a Need
          </Link>
        </section>
      )}
    </AppShell>
  );
}

function ActivityList({ title, items, kind, token }) {
  return (
    <section className="panel mini-table">
      <h2>{title}</h2>
      {items.map((item) => (
        <div key={item.id}>
          <i>{kind === 'need' ? '⚑' : '♡'}</i>
          <b>
            {kind === 'need' ? item.title : item.listing_title}
            <small>
              {kind === 'need' ? `${fmt(item.need_type)} · ${item.location}` : item.message || 'No message'}
            </small>
          </b>
          <strong>{kind === 'need' ? `₹${item.budget || 0}` : fmt(item.status)}</strong>
          {kind === 'sent' && item.status === 'ACCEPTED' && (
            <ContactReveal interestId={item.id} token={token} />
          )}
        </div>
      ))}
      {!items.length && <p className="empty">Nothing to show yet.</p>}
    </section>
  );
}

function Requests({ items, onRespond, busy, token }) {
  return (
    <section className="panel mini-table">
      <h2>Requests Received ({items.length})</h2>
      {items.map((item) => (
        <div key={item.id}>
          <i>✉</i>
          <b>
            {item.interested_user_name}
            <small>{item.listing_title}</small>
          </b>
          <strong>{item.message || 'No message'}</strong>
          <label className={item.status === 'ACCEPTED' ? 'status' : item.status === 'REJECTED' ? 'pink' : 'pending'}>
            {fmt(item.status)}
          </label>
          {item.status === 'PENDING' && (
            <span>
              <button
                className="primary compact"
                disabled={busy === item.id}
                onClick={() => onRespond(item.id, 'accept')}
              >
                Accept
              </button>
              <button
                className="danger compact"
                disabled={busy === item.id}
                onClick={() => onRespond(item.id, 'reject')}
              >
                Reject
              </button>
            </span>
          )}
          {item.status === 'ACCEPTED' && <ContactReveal interestId={item.id} token={token} />}
        </div>
      ))}
      {!items.length && <p className="empty">No requests received.</p>}
    </section>
  );
}

/**
 * Lazily reveals the counterparty's contact for an ACCEPTED interest.
 * Nothing is fetched (and no PII is exposed) until the user explicitly clicks,
 * which respects the backend contact rate-limiter. The endpoint still enforces
 * acceptance + participant membership server-side; this UI only surfaces it.
 */
function ContactReveal({ interestId, token }) {
  const [state, setState] = useState('idle'); // idle | loading | revealed | error
  const [contact, setContact] = useState(null);
  const [error, setError] = useState('');

  const reveal = async () => {
    setState('loading');
    setError('');
    try {
      const data = await api.contact(interestId, token);
      setContact(data);
      setState('revealed');
    } catch (e) {
      setError(e.message || 'Could not load contact details.');
      setState('error');
    }
  };

  if (state === 'revealed' && contact) {
    return (
      <span className="contact-reveal" style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <b>{contact.name}</b>
        <small>
          <a href={`mailto:${contact.email}`}>{contact.email}</a>
        </small>
        <small>
          <a href={`tel:${contact.phone}`}>{contact.phone}</a>
        </small>
      </span>
    );
  }

  return (
    <span className="contact-reveal">
      <button className="outline compact" disabled={state === 'loading'} onClick={reveal}>
        {state === 'loading' ? 'Revealing…' : 'Reveal contact'}
      </button>
      {state === 'error' && (
        <small className="error" style={{ marginLeft: 8 }}>
          {error}
        </small>
      )}
    </span>
  );
}
