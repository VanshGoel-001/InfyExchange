import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Inbox, LayoutDashboard, Megaphone, Package, ScrollText, Users } from 'lucide-react';
import { AppShell } from '../components/Layout';
import { Banner, Pill } from '../components/Ui';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import { CATEGORIES, LISTING_STATUSES, LISTING_TYPES, NEED_STATUSES, NEED_TYPES, ROLES, formatDateTime, formatPrice, labelOf, toneOf } from '../utils/labels';

const TABS = [
  ['overview', 'Overview', LayoutDashboard],
  ['users', 'Members', Users],
  ['listings', 'Items', Package],
  ['needs', 'Requests', Megaphone],
  ['audit', 'Admin log', ScrollText],
];

const LOG_ACTIONS = {
  UPDATE_USER: 'Changed a member',
  UPDATE_LISTING_STATUS: 'Changed an item’s availability',
  DELETE_LISTING: 'Deleted an item',
  DELETE_NEED: 'Deleted a request',
};

// "{"title":"Racket","old_status":"ACTIVE","new_status":"SOLD"}" -> "Racket: Available → Sold"
function describeLog(log) {
  let details;
  try {
    details = JSON.parse(log.details || 'null');
  } catch {
    return log.details || '';
  }
  if (!details) return '';
  const parts = [];
  if (details.title) parts.push(`“${details.title}”`);
  if (details.email) parts.push(details.email);
  if (details.old_status || details.new_status) {
    parts.push(`${labelOf(LISTING_STATUSES, details.old_status)} → ${labelOf(LISTING_STATUSES, details.new_status)}`);
  }
  for (const [field, change] of Object.entries(details.changes || {})) {
    const name = field === 'is_active' ? (change.to ? 'Reactivated' : 'Deactivated') : change.to ? 'Made admin' : 'Admin removed';
    parts.push(name);
  }
  return parts.join(' · ');
}

function SearchBar({ value, onChange, onSearch, placeholder }) {
  return (
    <form className="admin-search" onSubmit={(e) => { e.preventDefault(); onSearch(); }}>
      <input aria-label={placeholder} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      <button className="primary compact" type="submit">Search</button>
    </form>
  );
}

export default function AdminPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [rows, setRows] = useState({ users: null, listings: null, needs: null, audit: null });
  const [searchTerm, setSearchTerm] = useState('');
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    if (user && !user.is_admin) navigate('/profile', { replace: true });
  }, [user, navigate]);

  // `term` is passed in so a tab switch can load unfiltered without waiting for the state reset.
  const loadTab = async (name = tab, term = searchTerm) => {
    const query = term.trim() ? { search: term.trim() } : null;
    try {
      if (name === 'overview') {
        setStats(await api.adminStats(token));
        return;
      }
      const data = await {
        users: () => api.adminUsers(query, token),
        listings: () => api.adminListings(query, token),
        needs: () => api.adminNeeds(query, token),
        audit: () => api.adminAuditLogs(null, token),
      }[name]();
      setRows((current) => ({ ...current, [name]: data }));
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    if (!token || !user?.is_admin) return;
    setError('');
    setNotice('');
    setSearchTerm('');
    loadTab(tab, '');
  }, [tab, token]);

  // One place for "confirm, call the API, say what happened, refresh".
  const act = async ({ id, confirm, call, done, reload }) => {
    if (confirm && !window.confirm(confirm)) return;
    setBusyId(id);
    setError('');
    setNotice('');
    try {
      await call();
      setNotice(done);
      await loadTab(reload);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = (member) =>
    act({
      id: member.id,
      confirm: member.is_active
        ? `Deactivate ${member.email}? They will no longer be able to use InfyExchange until you reactivate them.`
        : `Reactivate ${member.email}?`,
      call: () => api.adminUpdateUser(member.id, { is_active: !member.is_active }, token),
      done: `${member.email} was ${member.is_active ? 'deactivated' : 'reactivated'}.`,
      reload: 'users',
    });

  const toggleAdmin = (member) =>
    act({
      id: member.id,
      confirm: member.is_admin
        ? `Remove admin access from ${member.email}?`
        : `Give ${member.email} admin access? Admins can delete any item or request and deactivate members.`,
      call: () => api.adminUpdateUser(member.id, { is_admin: !member.is_admin }, token),
      done: member.is_admin ? `${member.email} is no longer an admin.` : `${member.email} is now an admin.`,
      reload: 'users',
    });

  const setListingStatus = (item, status) =>
    act({
      id: item.id,
      call: () => api.adminListingStatus(item.id, status, token),
      done: `“${item.title}” is now marked ${labelOf(LISTING_STATUSES, status).toLowerCase()}.`,
      reload: 'listings',
    });

  const removeListing = (item) =>
    act({
      id: item.id,
      confirm: `Delete “${item.title}” for good? This is recorded in the Admin log.`,
      call: () => api.adminDeleteListing(item.id, token),
      done: `“${item.title}” was deleted.`,
      reload: 'listings',
    });

  const removeNeed = (need) =>
    act({
      id: need.id,
      confirm: `Delete the request “${need.title}” for good? This is recorded in the Admin log.`,
      call: () => api.adminDeleteNeed(need.id, token),
      done: `“${need.title}” was deleted.`,
      reload: 'needs',
    });

  const loading = (name) => rows[name] == null && !error;

  const statCards = stats && [
    [Users, `${stats.active_users} of ${stats.total_users}`, 'Members who can log in'],
    [Package, `${stats.active_listings} of ${stats.total_listings}`, 'Items still available'],
    [Megaphone, `${stats.active_needs} of ${stats.total_needs}`, 'Requests still open'],
    [Inbox, `${stats.accepted_interests} of ${stats.total_interests}`, 'Enquiries accepted'],
  ];

  return (
    <AppShell>
      <Banner title="Admin" subtitle="Look after members, items and requests. Everything you change is recorded." />

      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p role="status" className="flash">{notice}</p>}

      <div className="tabs" role="tablist" aria-label="Admin sections">
        {TABS.map(([key, label, Icon]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            <Icon aria-hidden="true" /> {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div>
          <div className="panel summary">
            <h2>Right now</h2>
            <div>
              {(statCards || [[Users, '—', 'Members who can log in'], [Package, '—', 'Items still available'], [Megaphone, '—', 'Requests still open'], [Inbox, '—', 'Enquiries accepted']]).map(([Icon, value, name]) => (
                <article className="stat" key={name}>
                  <Icon aria-hidden="true" />
                  <b>{value}<small>{name}</small></b>
                </article>
              ))}
            </div>
          </div>
          <div className="panel">
            <h3>Admin log</h3>
            <p className="form-lead">
              Every change made on this page is saved in the Admin log with who did it, when, and from which network address. Entries cannot be edited or deleted here.
            </p>
          </div>
        </div>
      )}

      {tab === 'users' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Members <small>({rows.users?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('users')} placeholder="Search name or email" />
          </div>
          <div className="table-scroll">
            <div className="table-head" style={{ '--cols': '1.3fr 1.7fr 1fr .8fr .9fr 1.7fr' }}>
              <span>Name</span><span>Email</span><span>Phone</span><span>Role</span><span>Status</span><span>Actions</span>
            </div>
            {rows.users?.items.map((u) => (
              <div className="table-row" key={u.id} style={{ '--cols': '1.3fr 1.7fr 1fr .8fr .9fr 1.7fr' }}>
                <b>{u.name} {u.is_admin && <Pill tone="blue">Admin</Pill>}</b>
                <span className="wrap">{u.email}</span>
                <small>{u.phone || 'Not added yet'}</small>
                <span>{u.role ? labelOf(ROLES, u.role) : '—'}</span>
                <span><Pill tone={u.is_active ? 'status' : 'pink'}>{u.is_active ? 'Active' : 'Deactivated'}</Pill></span>
                <span className="button-row">
                  <button className={u.is_active ? 'danger compact' : 'primary compact'} disabled={busyId === u.id || u.id === user.id} onClick={() => toggleActive(u)}>
                    {u.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                  <button className="outline compact" disabled={busyId === u.id || u.id === user.id} onClick={() => toggleAdmin(u)}>
                    {u.is_admin ? 'Remove admin' : 'Make admin'}
                  </button>
                </span>
              </div>
            ))}
          </div>
          {loading('users') && <p className="empty">Loading…</p>}
          {rows.users && !rows.users.items.length && <p className="empty">No members found.</p>}
        </section>
      )}

      {tab === 'listings' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Items <small>({rows.listings?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('listings')} placeholder="Search item name" />
          </div>
          <div className="table-scroll">
            <div className="table-head" style={{ '--cols': '2fr 1.2fr .8fr 1.2fr .7fr .8fr' }}>
              <span>Item and owner</span><span>Category</span><span>Price</span><span>Availability</span><span>Photos</span><span>Actions</span>
            </div>
            {rows.listings?.items.map((item) => (
              <div className="table-row" key={item.id} style={{ '--cols': '2fr 1.2fr .8fr 1.2fr .7fr .8fr' }}>
                <b>{item.title} <small>{item.owner_name} · {item.owner_email}</small></b>
                <small>{labelOf(CATEGORIES, item.category)} · {labelOf(LISTING_TYPES, item.listing_type)}</small>
                <b>{formatPrice(item.price)}</b>
                <span>
                  <select
                    aria-label={`Availability of ${item.title}`}
                    value={item.status}
                    disabled={busyId === item.id}
                    onChange={(e) => setListingStatus(item, e.target.value)}
                  >
                    {LISTING_STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </span>
                <small>{item.image_count} {item.image_count === 1 ? 'photo' : 'photos'}</small>
                <span>
                  <button className="danger compact" disabled={busyId === item.id} onClick={() => removeListing(item)}>Delete</button>
                </span>
              </div>
            ))}
          </div>
          {loading('listings') && <p className="empty">Loading…</p>}
          {rows.listings && !rows.listings.items.length && <p className="empty">No items found.</p>}
        </section>
      )}

      {tab === 'needs' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Requests <small>({rows.needs?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('needs')} placeholder="Search request title" />
          </div>
          <div className="table-scroll">
            <div className="table-head" style={{ '--cols': '2fr 1.4fr .8fr 1fr .8fr' }}>
              <span>Request and member</span><span>Category</span><span>Budget</span><span>Status</span><span>Actions</span>
            </div>
            {rows.needs?.items.map((n) => (
              <div className="table-row" key={n.id} style={{ '--cols': '2fr 1.4fr .8fr 1fr .8fr' }}>
                <b>{n.title} <small>{n.user_name} · {n.user_email}</small></b>
                <small>{labelOf(CATEGORIES, n.category)} · {labelOf(NEED_TYPES, n.need_type)}</small>
                <b>{n.budget > 0 ? formatPrice(n.budget) : '—'}</b>
                <span><Pill tone={toneOf(NEED_STATUSES, n.status)}>{labelOf(NEED_STATUSES, n.status)}</Pill></span>
                <span>
                  <button className="danger compact" disabled={busyId === n.id} onClick={() => removeNeed(n)}>Delete</button>
                </span>
              </div>
            ))}
          </div>
          {loading('needs') && <p className="empty">Loading…</p>}
          {rows.needs && !rows.needs.items.length && <p className="empty">No requests found.</p>}
        </section>
      )}

      {tab === 'audit' && (
        <section className="panel table">
          <h2>Admin log <small>({rows.audit?.total ?? '…'} entries)</small></h2>
          <div className="table-scroll">
            <div className="table-head" style={{ '--cols': '1.2fr 1.2fr 1.3fr 2.2fr' }}>
              <span>When</span><span>Who</span><span>What they did</span><span>Details</span>
            </div>
            {rows.audit?.items.map((log) => (
              <div className="table-row" key={log.id} style={{ '--cols': '1.2fr 1.2fr 1.3fr 2.2fr' }}>
                <small>{formatDateTime(log.created_at)}</small>
                <b>{log.actor_name || 'Removed member'} <small>{log.ip_address || ''}</small></b>
                <span>{LOG_ACTIONS[log.action] || log.action}</span>
                <small className="wrap">{describeLog(log)}</small>
              </div>
            ))}
          </div>
          {loading('audit') && <p className="empty">Loading…</p>}
          {rows.audit && !rows.audit.items.length && <p className="empty">Nothing has been logged yet.</p>}
        </section>
      )}
    </AppShell>
  );
}
