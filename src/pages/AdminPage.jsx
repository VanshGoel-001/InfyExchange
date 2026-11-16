import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Copy, Flag, Inbox, LayoutDashboard, Mail, MapPin, Megaphone, Package, ScrollText, Trash2, Users } from 'lucide-react';
import { AppShell } from '../components/Layout';
import { Banner, Pill } from '../components/Ui';
import { useAuth } from '../context/AuthContext';
import { api, safe, toFailure } from '../services/api';
import { InlineError, SectionBoundary } from '../components/Section';
import {
  CATEGORIES,
  INTEREST_STATUSES,
  LISTING_STATUSES,
  LISTING_TYPES,
  NEED_STATUSES,
  NEED_TYPES,
  REMOVAL_REASONS,
  ROLES,
  formatDateTime,
  formatPrice,
  labelOf,
  toneOf,
} from '../utils/labels';

const TABS = [
  ['overview', 'Overview', LayoutDashboard],
  ['users', 'Members', Users],
  ['listings', 'Listings', Package],
  ['needs', 'Needs', Megaphone],
  ['removals', 'Removed', Trash2],
  ['areas', 'Pickup areas', MapPin],
  ['reports', 'Reports', Flag],
  ['emails', 'Failed emails', Mail],
  ['audit', 'Admin log', ScrollText],
];

// What each tab can be narrowed by: [value, label] pairs. The value goes to the API as ?status= or ?status_filter=.
const FILTERS = {
  users: [['', 'All'], ['active', 'Active'], ['deactivated', 'Deactivated']],
  listings: [['', 'All'], ...LISTING_STATUSES.map((s) => [s.value, s.label])],
  needs: [['', 'All'], ...NEED_STATUSES.map((s) => [s.value, s.label])],
  removals: [['', 'All'], ...REMOVAL_REASONS.map((r) => [r.value, r.label])],
};

const LOG_ACTIONS = {
  UPDATE_USER: 'Changed a member',
  UPDATE_LISTING_STATUS: 'Changed a listing’s availability',
  DELETE_LISTING: 'Deleted a listing',
  DELETE_NEED: 'Deleted a need',
  CREATE_PICKUP_AREA: 'Added a pickup area',
  UPDATE_PICKUP_AREA: 'Changed a pickup area',
  RETRY_EMAIL: 'Retried a failed email',
  DISCARD_EMAIL: 'Discarded a failed email',
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
  if (log.action === 'CREATE_PICKUP_AREA') return details.name;
  if (log.action === 'UPDATE_PICKUP_AREA') {
    const changes = Object.entries(details.changes || {}).map(([field, change]) => {
      if (field === 'name') return `renamed from “${change.old}”`;
      if (field === 'is_active') return change.new ? 'reactivated' : 'deactivated';
      return change.new ? 'now has block numbers' : 'no longer has block numbers';
    });
    return [details.area, ...changes].filter(Boolean).join(' · ');
  }
  const parts = [];
  if (details.title) parts.push(`“${details.title}”`);
  if (details.reason) parts.push(`Reason: ${details.reason}`);
  if (details.email) parts.push(details.email);
  if (details.subject) parts.push(`“${details.subject}”`);
  if (details.result) parts.push(details.result === 'sent' ? 'Sent' : 'Failed again');
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

function FilterChips({ options, value, onChange }) {
  return (
    <div className="filter-chips" role="group" aria-label="Show">
      {options.map(([key, label]) => (
        <button key={key || 'all'} type="button" aria-pressed={value === key} className={value === key ? 'active' : ''} onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  );
}

// Grey placeholder rows that hold the shape of the list while it loads.
function Skeleton({ rows = 4 }) {
  return (
    <div className="skeleton-list" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

export default function AdminPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState(null);
  const [recentFailure, setRecentFailure] = useState(null);
  // The last failure (kind, message, ref) or null; never a raw message string.
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');
  const [rows, setRows] = useState({ users: null, listings: null, needs: null, removals: null, areas: null, reports: null, emails: null, audit: null });
  const [filters, setFilters] = useState({ users: '', listings: '', needs: '', removals: '' });
  const [newArea, setNewArea] = useState({ name: '', has_blocks: false });
  const [searchTerm, setSearchTerm] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [copied, setCopied] = useState(null);

  useEffect(() => {
    if (user && !user.is_admin) navigate('/profile', { replace: true });
  }, [user, navigate]);

  // `term` and `filter` are passed in so a tab switch can load straight away without waiting for state to settle.
  const loadTab = async (name = tab, term = searchTerm, filter = filters[name]) => {
    const query = {};
    if (term.trim()) query.search = term.trim();
    if (filter) query[{ users: 'status', removals: 'reason' }[name] ?? 'status_filter'] = filter;
    const params = Object.keys(query).length ? query : null;
    setError(null);
    if (name === 'overview') {
      // The counts and the latest log entries are separate requests: one failing must not hide the other.
      const [overview, log] = await Promise.all([safe(api.adminStats(token)), safe(api.adminAuditLogs({ limit: 5 }, token))]);
      if (overview.aborted || log.aborted) return;
      if (overview.ok) setStats(overview.data);
      else setError(overview.error);
      if (log.ok) {
        setRecent(log.data.items);
        setRecentFailure(null);
      } else {
        setRecentFailure(log.error);
      }
      return;
    }
    const result = await safe(
      {
        users: () => api.adminUsers(params, token),
        listings: () => api.adminListings(params, token),
        needs: () => api.adminNeeds(params, token),
        removals: () => api.adminRemovals(params, token),
        areas: () => api.adminPickupAreas(token),
        reports: () => api.adminReports(token),
        emails: () => api.adminFailedEmails(token),
        audit: () => api.adminAuditLogs(null, token),
      }[name]()
    );
    if (result.aborted) return;
    if (result.ok) setRows((current) => ({ ...current, [name]: result.data }));
    else setError(result.error);
  };

  useEffect(() => {
    if (!token || !user?.is_admin) return;
    setError(null);
    setNotice('');
    setSearchTerm('');
    loadTab(tab, '', filters[tab]);
  }, [tab, token]);

  // Keep the chosen tab in view when the row of tabs has to scroll sideways.
  useEffect(() => {
    document.querySelector('.tabs button.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [tab]);

  // Cards on the overview open the tab they count, already narrowed to what the card shows.
  const openTab = (name, filter = '') => {
    if (name in filters) setFilters((current) => ({ ...current, [name]: filter }));
    setTab(name);
  };

  const changeFilter = (name, value) => {
    setFilters((current) => ({ ...current, [name]: value }));
    loadTab(name, searchTerm, value);
  };

  // One place for "confirm, call the API, say what happened, refresh".
  const act = async ({ id, confirm, call, done, reload }) => {
    if (confirm && !window.confirm(confirm)) return;
    setBusyId(id);
    setError(null);
    setNotice('');
    try {
      await call();
      setNotice(done);
      await loadTab(reload);
    } catch (err) {
      setError(toFailure(err));
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = (member) =>
    act({
      id: member.id,
      confirm: member.is_active
        ? `Deactivate ${member.name} (${member.email})?\n\nThey will no longer be able to log in or use InfyExchange until you reactivate them. This is recorded in the Admin log.`
        : `Reactivate ${member.name} (${member.email})?\n\nThey will be able to log in and use InfyExchange again. This is recorded in the Admin log.`,
      call: () => api.adminUpdateUser(member.id, { is_active: !member.is_active }, token),
      done: `${member.email} was ${member.is_active ? 'deactivated' : 'reactivated'}.`,
      reload: 'users',
    });

  const toggleAdmin = (member) =>
    act({
      id: member.id,
      confirm: member.is_admin
        ? `Remove admin access from ${member.name} (${member.email})?\n\nThey will no longer see the Admin pages or be able to change other members. This is recorded in the Admin log.`
        : `Make ${member.name} (${member.email}) an admin?\n\nAdmins can delete any listing or need, deactivate members and see their phone numbers. This is recorded in the Admin log.`,
      call: () => api.adminUpdateUser(member.id, { is_admin: !member.is_admin }, token),
      done: member.is_admin ? `${member.email} is no longer an admin.` : `${member.email} is now an admin.`,
      reload: 'users',
    });

  const copyPhone = async (member) => {
    try {
      await navigator.clipboard.writeText(member.phone);
      setCopied(member.id);
      setTimeout(() => setCopied((current) => (current === member.id ? null : current)), 1800);
    } catch {
      setNotice(`Could not copy automatically. The number is ${member.phone}.`);
    }
  };

  const setListingStatus = (item, status) =>
    act({
      id: item.id,
      call: () => api.adminListingStatus(item.id, status, token),
      done: `“${item.title}” is now marked ${labelOf(LISTING_STATUSES, status).toLowerCase()}.`,
      reload: 'listings',
    });

  // A removal has to say why: the owner is shown this text, and it is kept in the Admin log and the Removed tab.
  const askReason = (what) => {
    const answer = window.prompt(`Why are you deleting ${what} for good?

The owner will be shown this reason. It is also recorded in the Admin log.`, '');
    if (answer === null) return null;
    const reason = answer.trim();
    if (reason.length < 3 || reason.length > 200) {
      setNotice('');
      setError({ kind: 'invalid', message: 'Give a reason of 3 to 200 characters. Nothing was deleted.' });
      return null;
    }
    return reason;
  };

  const removeListing = (item) => {
    const reason = askReason(`“${item.title}”`);
    if (!reason) return undefined;
    return act({
      id: item.id,
      call: () => api.adminDeleteListing(item.id, reason, token),
      done: `“${item.title}” was deleted.`,
      reload: 'listings',
    });
  };

  const removeNeed = (need) => {
    const reason = askReason(`the need “${need.title}”`);
    if (!reason) return undefined;
    return act({
      id: need.id,
      call: () => api.adminDeleteNeed(need.id, reason, token),
      done: `“${need.title}” was deleted.`,
      reload: 'needs',
    });
  };

  const addArea = async (event) => {
    event.preventDefault();
    await act({
      id: 'new-area',
      call: () => api.adminCreatePickupArea({ name: newArea.name, has_blocks: newArea.has_blocks }, token),
      done: `“${newArea.name.trim()}” was added.`,
      reload: 'areas',
    });
    setNewArea({ name: '', has_blocks: false });
  };

  const changeArea = (area, body, done, confirm) =>
    act({ id: area.id, confirm, call: () => api.adminUpdatePickupArea(area.id, body, token), done, reload: 'areas' });

  const renameArea = (area) => {
    const name = window.prompt('New name for this pickup area. Listings already posted there will show the new name.', area.name);
    if (name && name.trim() && name.trim() !== area.name) changeArea(area, { name }, `“${area.name}” is now “${name.trim()}”.`);
  };

  const retryEmail = (mail) =>
    act({
      id: mail.id,
      call: () => api.adminRetryEmail(mail.id, token),
      done: 'The email was sent.',
      reload: 'emails',
    });

  const discardEmail = (mail) =>
    act({
      id: mail.id,
      confirm: `Discard “${mail.subject}” to ${mail.to_email}? It will not be sent. This is recorded in the Admin log.`,
      call: () => api.adminDiscardEmail(mail.id, token),
      done: 'The email was discarded.',
      reload: 'emails',
    });

  // A tab whose data has not arrived shows placeholder rows, or a retry if the request failed.
  const waiting = (name) => {
    if (rows[name] != null) return null;
    return error ? <InlineError error={error} context="generic" onRetry={() => loadTab(name)} /> : <Skeleton />;
  };

  const hasData = tab === 'overview' ? stats != null : rows[tab] != null;

  const deactivated = stats ? stats.total_users - stats.active_users : 0;

  return (
    <AppShell>
      <Banner title="Admin" subtitle="Look after members, listings and needs. Everything you change is recorded." />

      {error && hasData && <InlineError error={error} context="generic" onRetry={() => setError(null)} />}
      {notice && <p role="status" className="flash">{notice}</p>}

      <div className="tabs" role="tablist" aria-label="Admin sections">
        {TABS.map(([key, label, Icon]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            <Icon aria-hidden="true" /> {label}
          </button>
        ))}
      </div>

      <SectionBoundary key={tab} name={`admin ${tab}`} context="generic">
      {tab === 'overview' && (
        <div className="admin-overview">
          {!stats && !error && <Skeleton rows={3} />}
          {!stats && error && (
            <div className="stat-grid">
              {[['Active members', Users], ['Available listings', Package], ['Open needs', Megaphone], ['Enquiries', Inbox]].map(([label, Icon]) => (
                <article className="stat-card" key={label}>
                  <div className="stat-main static">
                    <Icon aria-hidden="true" />
                    <span>{label}</span>
                    <b className="stat-unavailable">—</b>
                  </div>
                  <InlineError error={error} context="stat" compact onRetry={() => loadTab('overview')} />
                </article>
              ))}
            </div>
          )}
          {stats && (
            <>
              <div className="stat-grid">
                <article className="stat-card">
                  <button type="button" className="stat-main" onClick={() => openTab('users', 'active')}>
                    <Users aria-hidden="true" />
                    <span>Active members</span>
                    <b>{stats.active_users} of {stats.total_users}</b>
                  </button>
                  {deactivated > 0 ? (
                    <button type="button" className="stat-link" onClick={() => openTab('users', 'deactivated')}>{deactivated} deactivated</button>
                  ) : (
                    <small>None deactivated</small>
                  )}
                </article>
                <article className="stat-card">
                  <button type="button" className="stat-main" onClick={() => openTab('listings', 'ACTIVE')}>
                    <Package aria-hidden="true" />
                    <span>Available listings</span>
                    <b>{stats.active_listings} of {stats.total_listings}</b>
                  </button>
                  <small>{stats.total_listings - stats.active_listings} sold, lent out or unavailable</small>
                </article>
                <article className="stat-card">
                  <button type="button" className="stat-main" onClick={() => openTab('needs', 'ACTIVE')}>
                    <Megaphone aria-hidden="true" />
                    <span>Open needs</span>
                    <b>{stats.active_needs} of {stats.total_needs}</b>
                  </button>
                  <small>{stats.total_needs - stats.active_needs} fulfilled or closed</small>
                </article>
                <article className="stat-card">
                  <div className="stat-main static">
                    <Inbox aria-hidden="true" />
                    <span>Enquiries</span>
                    <b>{stats.total_interests}</b>
                  </div>
                  <ul className="stat-split">
                    {[['ACCEPTED', stats.accepted_interests], ['PENDING', stats.pending_interests], ['REJECTED', stats.rejected_interests]].map(([status, count]) => (
                      <li key={status}><b>{count}</b> {labelOf(INTEREST_STATUSES, status)}</li>
                    ))}
                  </ul>
                </article>
              </div>

              <section className="panel attention" aria-labelledby="attention-title">
                <h3 id="attention-title">Needs your attention</h3>
                {stats.total_reports + stats.failed_emails === 0 ? (
                  <p className="all-clear"><Check aria-hidden="true" /> Nothing needs your attention right now.</p>
                ) : (
                  <div className="attention-row">
                    {stats.total_reports > 0 && (
                      <button type="button" className="attention-item" onClick={() => openTab('reports')}>
                        <Flag aria-hidden="true" /> <b>{stats.total_reports}</b> {stats.total_reports === 1 ? 'report' : 'reports'} to review
                      </button>
                    )}
                    {stats.failed_emails > 0 && (
                      <button type="button" className="attention-item" onClick={() => openTab('emails')}>
                        <Mail aria-hidden="true" /> <b>{stats.failed_emails}</b> {stats.failed_emails === 1 ? 'email' : 'emails'} could not be sent
                      </button>
                    )}
                  </div>
                )}
              </section>

              <section className="panel recent" aria-labelledby="recent-title">
                <div className="recent-head">
                  <h3 id="recent-title">Latest admin activity</h3>
                  <button type="button" className="stat-link" onClick={() => openTab('audit')}>View all</button>
                </div>
                {recentFailure && !recent ? (
                  <InlineError error={recentFailure} context="generic" onRetry={() => loadTab('overview')} />
                ) : !recent ? (
                  <Skeleton rows={2} />
                ) : recent.length ? (
                  <ul>
                    {recent.map((log) => (
                      <li key={log.id}>
                        <span>
                          <b>{log.actor_name || 'Removed member'}</b> {(LOG_ACTIONS[log.action] || log.action).toLowerCase()}
                          {describeLog(log) && <small> · {describeLog(log)}</small>}
                        </span>
                        <time dateTime={log.created_at}>{formatDateTime(log.created_at)}</time>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty">Nothing has been logged yet.</p>
                )}
              </section>
            </>
          )}
        </div>
      )}

      {tab === 'users' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Members <small>({rows.users?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('users')} placeholder="Search name or email" />
          </div>
          <FilterChips options={FILTERS.users} value={filters.users} onChange={(value) => changeFilter('users', value)} />
          {waiting('users')}
          {rows.users && (
            <ul className="member-list">
              {rows.users.items.map((u) => {
                const self = u.id === user.id;
                return (
                  <li className="member" key={u.id}>
                    <div className="member-top">
                      <b>{u.name}</b>
                      {u.is_admin && <Pill tone="blue">Admin</Pill>}
                      {u.role && <Pill tone="purple">{labelOf(ROLES, u.role)}</Pill>}
                      {!u.is_active && <Pill tone="pink">Deactivated</Pill>}
                    </div>
                    <span className="member-email">{u.email}</span>
                    <dl className="member-meta">
                      <div>
                        <dt>Phone</dt>
                        <dd>
                          {u.phone ? (
                            <button type="button" className="copy" onClick={() => copyPhone(u)} aria-label={`Copy phone number ${u.phone}`}>
                              {u.phone}
                              {copied === u.id ? <><Check aria-hidden="true" /> Copied</> : <Copy aria-hidden="true" />}
                            </button>
                          ) : (
                            'Not added yet'
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Role</dt>
                        <dd>{u.role ? ROLES.find((r) => r.value === u.role)?.option || u.role : 'Not chosen yet'}</dd>
                      </div>
                    </dl>
                    <div className="member-actions">
                      <button type="button" className="outline" disabled={busyId === u.id || self} onClick={() => toggleAdmin(u)}>
                        {u.is_admin ? 'Remove admin' : 'Make admin'}
                      </button>
                      <button type="button" className={u.is_active ? 'danger' : 'primary'} disabled={busyId === u.id || self} onClick={() => toggleActive(u)}>
                        {u.is_active ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </div>
                    {self && <small className="member-note">This is you, so these can’t be changed here.</small>}
                  </li>
                );
              })}
            </ul>
          )}
          {rows.users && !rows.users.items.length && <p className="empty">No members found.</p>}
        </section>
      )}

      {tab === 'listings' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Listings <small>({rows.listings?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('listings')} placeholder="Search listing name" />
          </div>
          <FilterChips options={FILTERS.listings} value={filters.listings} onChange={(value) => changeFilter('listings', value)} />
          {waiting('listings')}
          {rows.listings && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '2fr 1.2fr .8fr 1.2fr .7fr .8fr' }}>
                <span>Listing and owner</span><span>Category</span><span>Price</span><span>Availability</span><span>Photos</span><span>Actions</span>
              </div>
              {rows.listings.items.map((item) => (
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
          )}
          {rows.listings && !rows.listings.items.length && <p className="empty">No listings found.</p>}
        </section>
      )}

      {tab === 'needs' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Needs <small>({rows.needs?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('needs')} placeholder="Search need title" />
          </div>
          <FilterChips options={FILTERS.needs} value={filters.needs} onChange={(value) => changeFilter('needs', value)} />
          {waiting('needs')}
          {rows.needs && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '2fr 1.4fr .8fr 1fr .8fr' }}>
                <span>Need and member</span><span>Category</span><span>Budget</span><span>Status</span><span>Actions</span>
              </div>
              {rows.needs.items.map((n) => (
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
          )}
          {rows.needs && !rows.needs.items.length && <p className="empty">No needs found.</p>}
        </section>
      )}

      {tab === 'removals' && (
        <section className="panel table">
          <div className="admin-head">
            <h2>Removed <small>({rows.removals?.total ?? '…'})</small></h2>
            <SearchBar value={searchTerm} onChange={setSearchTerm} onSearch={() => loadTab('removals')} placeholder="Search title or owner" />
          </div>
          <p className="form-lead">Listings and needs that are gone: who removed them, when and why. Kept for 90 days. Removals from before this list existed are not shown.</p>
          <FilterChips options={FILTERS.removals} value={filters.removals} onChange={(value) => changeFilter('removals', value)} />
          {waiting('removals')}
          {rows.removals && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '1.1fr 2fr 1.2fr 1.3fr 1.6fr' }}>
                <span>When</span><span>What</span><span>Owner</span><span>Removed by</span><span>Why</span>
              </div>
              {rows.removals.items.map((r) => (
                <div className="table-row" key={r.id} style={{ '--cols': '1.1fr 2fr 1.2fr 1.3fr 1.6fr' }}>
                  <small>{formatDateTime(r.created_at)}</small>
                  <b>
                    {r.title}
                    <small>
                      {[r.kind === 'NEED' ? 'Need' : 'Listing', labelOf(CATEGORIES, r.category), labelOf(r.kind === 'NEED' ? NEED_TYPES : LISTING_TYPES, r.item_type), r.amount > 0 ? formatPrice(r.amount) : '']
                        .filter(Boolean)
                        .join(' · ')}
                    </small>
                  </b>
                  <span>{r.owner_name || 'Removed member'}</span>
                  <span>{r.removed_by_id ? (r.removed_by_id === r.owner_id ? 'The owner' : r.removed_by_name || 'Removed member') : 'Nobody (expired)'}</span>
                  <span>
                    <Pill tone={toneOf(REMOVAL_REASONS, r.reason)}>{labelOf(REMOVAL_REASONS, r.reason)}</Pill>
                    {r.note && <small className="wrap">{r.note}</small>}
                  </span>
                </div>
              ))}
            </div>
          )}
          {rows.removals && !rows.removals.items.length && <p className="empty">Nothing has been removed.</p>}
        </section>
      )}

      {tab === 'areas' && (
        <section className="panel table">
          <h2>Pickup areas <small>({rows.areas?.length ?? '…'})</small></h2>
          <p className="form-lead">The places people can pick an item up from. Turn on block numbers for areas such as ECC that have numbered blocks. A hidden area stays on listings already posted but cannot be chosen for new ones.</p>
          <form className="inline area-add" onSubmit={addArea}>
            <input
              aria-label="Name of the new pickup area"
              value={newArea.name}
              maxLength={60}
              onChange={(e) => setNewArea((a) => ({ ...a, name: e.target.value }))}
              placeholder="e.g. Sports Hall"
            />
            <label className="check">
              <input type="checkbox" checked={newArea.has_blocks} onChange={(e) => setNewArea((a) => ({ ...a, has_blocks: e.target.checked }))} />
              Has block numbers
            </label>
            <button className="primary compact" type="submit" disabled={!newArea.name.trim() || busyId === 'new-area'}>Add area</button>
          </form>
          {waiting('areas')}
          {rows.areas && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '1.6fr 1fr 1fr 2fr' }}>
                <span>Name</span><span>Block numbers</span><span>Shown to members</span><span />
              </div>
              {rows.areas.map((area) => (
                <div className="table-row" key={area.id} style={{ '--cols': '1.6fr 1fr 1fr 2fr' }}>
                  <b>{area.name}</b>
                  <span>{area.has_blocks ? 'Yes' : 'No'}</span>
                  <span>{area.is_active ? 'Yes' : 'Hidden'}</span>
                  <span className="button-row">
                    <button className="outline compact" disabled={busyId === area.id} onClick={() => renameArea(area)}>Rename</button>
                    <button
                      className="outline compact"
                      disabled={busyId === area.id}
                      onClick={() => changeArea(area, { has_blocks: !area.has_blocks }, `${area.name} ${area.has_blocks ? 'no longer has' : 'now has'} block numbers.`)}
                    >
                      {area.has_blocks ? 'Turn blocks off' : 'Turn blocks on'}
                    </button>
                    <button
                      className={area.is_active ? 'danger compact' : 'primary compact'}
                      disabled={busyId === area.id}
                      onClick={() =>
                        changeArea(
                          area,
                          { is_active: !area.is_active },
                          `${area.name} is now ${area.is_active ? 'hidden' : 'shown'}.`,
                          area.is_active ? `Hide ${area.name}? It will no longer be offered for new listings.` : undefined
                        )
                      }
                    >
                      {area.is_active ? 'Hide' : 'Show'}
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {tab === 'reports' && (
        <section className="panel table">
          <h2>Reports <small>({rows.reports?.total ?? '…'})</small></h2>
          {waiting('reports')}
          {rows.reports && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '1fr 1fr 1.6fr 2fr' }}>
                <span>When</span><span>Reported by</span><span>About</span><span>What they said</span>
              </div>
              {rows.reports.items.map((report) => (
                <div className="table-row" key={report.id} style={{ '--cols': '1fr 1fr 1.6fr 2fr' }}>
                  <small>{formatDateTime(report.created_at)}</small>
                  <b>{report.reporter_name}</b>
                  <span>
                    {report.reported_name} <small>{report.reported_email}</small>
                    {report.listing_title && <small> · {report.listing_title}</small>}
                  </span>
                  <small className="wrap">{report.reason}</small>
                </div>
              ))}
            </div>
          )}
          {rows.reports && !rows.reports.items.length && <p className="empty">No one has been reported.</p>}
        </section>
      )}

      {tab === 'emails' && (
        <section className="panel table">
          <h2>Failed emails <small>({rows.emails?.total ?? '…'})</small></h2>
          <p className="form-lead">Emails the provider would not accept. Retry sends the same message again; Discard drops it. Unresolved ones are removed after 30 days.</p>
          {waiting('emails')}
          {rows.emails && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '1fr 1.8fr 1.8fr .5fr 1.3fr' }}>
                <span>When</span><span>To and subject</span><span>Why it failed</span><span>Tries</span><span />
              </div>
              {rows.emails.items.map((mail) => (
                <div className="table-row" key={mail.id} style={{ '--cols': '1fr 1.8fr 1.8fr .5fr 1.3fr' }}>
                  <small>{formatDateTime(mail.created_at)}</small>
                  <span>{mail.to_email} <small>{mail.subject}</small></span>
                  <small className="wrap">{mail.error}</small>
                  <span>{mail.attempts}</span>
                  <span className="button-row">
                    <button className="primary compact" disabled={busyId === mail.id} onClick={() => retryEmail(mail)}>Retry</button>
                    <button className="danger compact" disabled={busyId === mail.id} onClick={() => discardEmail(mail)}>Discard</button>
                  </span>
                </div>
              ))}
            </div>
          )}
          {rows.emails && !rows.emails.items.length && <p className="empty">No failed emails.</p>}
        </section>
      )}

      {tab === 'audit' && (
        <section className="panel table">
          <h2>Admin log <small>({rows.audit?.total ?? '…'} entries)</small></h2>
          {waiting('audit')}
          {rows.audit && (
            <div className="table-scroll">
              <div className="table-head" style={{ '--cols': '1.2fr 1.2fr 1.3fr 2.2fr' }}>
                <span>When</span><span>Who</span><span>What they did</span><span>Details</span>
              </div>
              {rows.audit.items.map((log) => (
                <div className="table-row" key={log.id} style={{ '--cols': '1.2fr 1.2fr 1.3fr 2.2fr' }}>
                  <small>{formatDateTime(log.created_at)}</small>
                  <b>{log.actor_name || 'Removed member'} <small>{log.ip_address || ''}</small></b>
                  <span>{LOG_ACTIONS[log.action] || log.action}</span>
                  <small className="wrap">{describeLog(log)}</small>
                </div>
              ))}
            </div>
          )}
          {rows.audit && !rows.audit.items.length && <p className="empty">Nothing has been logged yet.</p>}
        </section>
      )}
      </SectionBoundary>
    </AppShell>
  );
}
