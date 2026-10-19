import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as I from 'lucide-react';
import { AppShell } from '../components/Layout';
import { Banner } from '../components/Ui';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';

export default function AdminPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview'); // overview | users | listings | needs | audit
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionNotice, setActionNotice] = useState('');

  // Tables state
  const [usersData, setUsersData] = useState({ items: [], total: 0 });
  const [listingsData, setListingsData] = useState({ items: [], total: 0 });
  const [needsData, setNeedsData] = useState({ items: [], total: 0 });
  const [auditData, setAuditData] = useState({ items: [], total: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    if (user && !user.is_admin) {
      navigate('/profile', { replace: true });
    }
  }, [user, navigate]);

  const loadStats = async () => {
    try {
      const data = await api.adminStats(token);
      setStats(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await api.adminUsers(searchTerm ? { search: searchTerm } : null, token);
      setUsersData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadListings = async () => {
    setLoading(true);
    try {
      const data = await api.adminListings(searchTerm ? { search: searchTerm } : null, token);
      setListingsData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadNeeds = async () => {
    setLoading(true);
    try {
      const data = await api.adminNeeds(searchTerm ? { search: searchTerm } : null, token);
      setNeedsData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadAuditLogs = async () => {
    setLoading(true);
    try {
      const data = await api.adminAuditLogs(null, token);
      setAuditData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token || !user?.is_admin) return;
    setError('');
    setActionNotice('');
    if (tab === 'overview') {
      loadStats();
    } else if (tab === 'users') {
      loadUsers();
    } else if (tab === 'listings') {
      loadListings();
    } else if (tab === 'needs') {
      loadNeeds();
    } else if (tab === 'audit') {
      loadAuditLogs();
    }
  }, [tab, token]);

  const toggleUserActive = async (targetUser) => {
    const nextState = !targetUser.is_active;
    if (!window.confirm(`Are you sure you want to ${nextState ? 'ACTIVATE' : 'DEACTIVATE'} user ${targetUser.email}?`)) return;
    setBusyId(targetUser.id);
    try {
      await api.adminUpdateUser(targetUser.id, { is_active: nextState }, token);
      setActionNotice(`User ${targetUser.email} status updated.`);
      loadUsers();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const toggleUserAdmin = async (targetUser) => {
    const nextState = !targetUser.is_admin;
    if (!window.confirm(`Are you sure you want to ${nextState ? 'GRANT' : 'REVOKE'} Admin privileges for ${targetUser.email}?`)) return;
    setBusyId(targetUser.id);
    try {
      await api.adminUpdateUser(targetUser.id, { is_admin: nextState }, token);
      setActionNotice(`User ${targetUser.email} admin rights updated.`);
      loadUsers();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const changeListingStatus = async (listingId, newStatus) => {
    setBusyId(listingId);
    try {
      await api.adminListingStatus(listingId, newStatus, token);
      setActionNotice(`Listing #${listingId} status set to ${newStatus}.`);
      loadListings();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const deleteListing = async (listingId, title) => {
    if (!window.confirm(`Permanently delete listing "${title}" (#${listingId})? This action is logged.`)) return;
    setBusyId(listingId);
    try {
      await api.adminDeleteListing(listingId, token);
      setActionNotice(`Listing #${listingId} deleted.`);
      loadListings();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const deleteNeed = async (needId, title) => {
    if (!window.confirm(`Permanently delete need request "${title}" (#${needId})? This action is logged.`)) return;
    setBusyId(needId);
    try {
      await api.adminDeleteNeed(needId, token);
      setActionNotice(`Need request #${needId} deleted.`);
      loadNeeds();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AppShell>
      <Banner
        title="Admin Control Plane"
        subtitle="Privileged internal operations, database transparency, user access, and audit ledger."
      />

      {error && <p role="alert" className="error" style={{ margin: '14px 0' }}>{error}</p>}
      {actionNotice && <p role="status" className="status" style={{ margin: '14px 0', padding: '10px 14px' }}>{actionNotice}</p>}

      {/* Admin Tabs */}
      <div className="tabs" style={{ marginBottom: '20px', cursor: 'pointer' }}>
        <b
          style={{ borderBottom: tab === 'overview' ? '3px solid #0874ee' : 'none', color: tab === 'overview' ? '#0874ee' : '#536176' }}
          onClick={() => setTab('overview')}
        >
          <I.LayoutDashboard style={{ width: 16, verticalAlign: 'middle', marginRight: 6 }} />
          Database Overview
        </b>
        <b
          style={{ borderBottom: tab === 'users' ? '3px solid #0874ee' : 'none', color: tab === 'users' ? '#0874ee' : '#536176' }}
          onClick={() => setTab('users')}
        >
          <I.Users style={{ width: 16, verticalAlign: 'middle', marginRight: 6 }} />
          Users & Access
        </b>
        <b
          style={{ borderBottom: tab === 'listings' ? '3px solid #0874ee' : 'none', color: tab === 'listings' ? '#0874ee' : '#536176' }}
          onClick={() => setTab('listings')}
        >
          <I.Package style={{ width: 16, verticalAlign: 'middle', marginRight: 6 }} />
          Listings Moderation
        </b>
        <b
          style={{ borderBottom: tab === 'needs' ? '3px solid #0874ee' : 'none', color: tab === 'needs' ? '#0874ee' : '#536176' }}
          onClick={() => setTab('needs')}
        >
          <I.Megaphone style={{ width: 16, verticalAlign: 'middle', marginRight: 6 }} />
          Needs Moderation
        </b>
        <b
          style={{ borderBottom: tab === 'audit' ? '3px solid #0874ee' : 'none', color: tab === 'audit' ? '#0874ee' : '#536176' }}
          onClick={() => setTab('audit')}
        >
          <I.ShieldAlert style={{ width: 16, verticalAlign: 'middle', marginRight: 6 }} />
          Audit Ledger (WORM)
        </b>
      </div>

      {/* TAB 1: Database Overview */}
      {tab === 'overview' && (
        <div>
          <div className="summary" style={{ marginBottom: '25px' }}>
            <h2>📊 Real-Time Database Metrics</h2>
            <div>
              <article>
                <span>👥</span>
                <b>
                  {stats ? `${stats.active_users} / ${stats.total_users}` : '—'}
                  <small>Active Users / Total</small>
                </b>
              </article>
              <article>
                <span>📦</span>
                <b>
                  {stats ? `${stats.active_listings} / ${stats.total_listings}` : '—'}
                  <small>Active Listings / Total</small>
                </b>
              </article>
              <article>
                <span>📢</span>
                <b>
                  {stats ? `${stats.active_needs} / ${stats.total_needs}` : '—'}
                  <small>Active Needs / Total</small>
                </b>
              </article>
              <article>
                <span>🤝</span>
                <b>
                  {stats ? `${stats.accepted_interests} / ${stats.total_interests}` : '—'}
                  <small>Accepted / Total Interests</small>
                </b>
              </article>
            </div>
          </div>

          <div className="panel" style={{ padding: '20px' }}>
            <h3>🔒 Operational Security & System State</h3>
            <p style={{ color: '#566276', lineHeight: 1.6 }}>
              All database mutations executed within this panel generate an immutable append-only record in the <strong>Audit Ledger</strong> including your identity, client IP, action type, and diff payload. User sessions enforce server-side role validation on every API invocation.
            </p>
          </div>
        </div>
      )}

      {/* TAB 2: Users Management */}
      {tab === 'users' && (
        <section className="panel table">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 }}>
            <h2>Users Management <small>({usersData.total} total)</small></h2>
            <form onSubmit={(e) => { e.preventDefault(); loadUsers(); }} style={{ display: 'flex', gap: 8 }}>
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search name or email..."
                style={{ width: 220 }}
              />
              <button className="primary" type="submit" style={{ padding: '6px 12px' }}>Search</button>
            </form>
          </div>

          <div className="table-head" style={{ gridTemplateColumns: '1.2fr 1.6fr 1fr 0.8fr 0.8fr 1.5fr' }}>
            <span>Name</span>
            <span>Email</span>
            <span>Phone</span>
            <span>Role</span>
            <span>Status</span>
            <span>Privileged Actions</span>
          </div>

          {usersData.items.map((u) => (
            <div className="table-row" key={u.id} style={{ gridTemplateColumns: '1.2fr 1.6fr 1fr 0.8fr 0.8fr 1.5fr' }}>
              <b>{u.name} {u.is_admin && <label className="blue" style={{ fontSize: 10, padding: '2px 5px' }}>ADMIN</label>}</b>
              <span>{u.email}</span>
              <small>{u.phone}</small>
              <span><label className="blue">{u.role}</label></span>
              <span>
                <label className={u.is_active ? 'status' : 'pink'}>
                  {u.is_active ? 'ACTIVE' : 'DEACTIVATED'}
                </label>
              </span>
              <span style={{ display: 'flex', gap: 6 }}>
                <button
                  className={u.is_active ? 'danger compact' : 'primary compact'}
                  disabled={busyId === u.id || u.id === user.id}
                  onClick={() => toggleUserActive(u)}
                >
                  {u.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button
                  className="outline compact"
                  disabled={busyId === u.id || u.id === user.id}
                  onClick={() => toggleUserAdmin(u)}
                >
                  {u.is_admin ? 'Revoke Admin' : 'Make Admin'}
                </button>
              </span>
            </div>
          ))}
          {!usersData.items.length && <p className="empty">No users found.</p>}
        </section>
      )}

      {/* TAB 3: Listings Moderation */}
      {tab === 'listings' && (
        <section className="panel table">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 }}>
            <h2>Listings Moderation <small>({listingsData.total} total)</small></h2>
            <form onSubmit={(e) => { e.preventDefault(); loadListings(); }} style={{ display: 'flex', gap: 8 }}>
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search listing title..."
                style={{ width: 220 }}
              />
              <button className="primary" type="submit" style={{ padding: '6px 12px' }}>Search</button>
            </form>
          </div>

          <div className="table-head" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1.6fr' }}>
            <span>Item & Owner</span>
            <span>Category</span>
            <span>Price</span>
            <span>Status</span>
            <span>Photos</span>
            <span>Moderation Actions</span>
          </div>

          {listingsData.items.map((item) => (
            <div className="table-row" key={item.id} style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1.6fr' }}>
              <div>
                <b>{item.title} <small>Owner: {item.owner_name} ({item.owner_email})</small></b>
              </div>
              <small>{item.category} / {item.listing_type}</small>
              <b>₹{item.price}</b>
              <span>
                <select
                  value={item.status}
                  disabled={busyId === item.id}
                  onChange={(e) => changeListingStatus(item.id, e.target.value)}
                  style={{ height: 28, fontSize: 12, padding: '2px 6px' }}
                >
                  {['ACTIVE', 'SOLD', 'RENTED', 'UNAVAILABLE'].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </span>
              <small>{item.image_count} photo(s)</small>
              <span>
                <button
                  className="danger compact"
                  disabled={busyId === item.id}
                  onClick={() => deleteListing(item.id, item.title)}
                >
                  Delete
                </button>
              </span>
            </div>
          ))}
          {!listingsData.items.length && <p className="empty">No listings found.</p>}
        </section>
      )}

      {/* TAB 4: Needs Moderation */}
      {tab === 'needs' && (
        <section className="panel table">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 }}>
            <h2>Needs Requests Moderation <small>({needsData.total} total)</small></h2>
            <form onSubmit={(e) => { e.preventDefault(); loadNeeds(); }} style={{ display: 'flex', gap: 8 }}>
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search need title..."
                style={{ width: 220 }}
              />
              <button className="primary" type="submit" style={{ padding: '6px 12px' }}>Search</button>
            </form>
          </div>

          <div className="table-head" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1.2fr' }}>
            <span>Need & Requester</span>
            <span>Category</span>
            <span>Budget</span>
            <span>Status</span>
            <span>Actions</span>
          </div>

          {needsData.items.map((n) => (
            <div className="table-row" key={n.id} style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1.2fr' }}>
              <div>
                <b>{n.title} <small>Requester: {n.user_name} ({n.user_email})</small></b>
              </div>
              <small>{n.category} / {n.need_type}</small>
              <b>₹{n.budget}</b>
              <span><label className="blue">{n.status}</label></span>
              <span>
                <button
                  className="danger compact"
                  disabled={busyId === n.id}
                  onClick={() => deleteNeed(n.id, n.title)}
                >
                  Delete
                </button>
              </span>
            </div>
          ))}
          {!needsData.items.length && <p className="empty">No needs requests found.</p>}
        </section>
      )}

      {/* TAB 5: Audit Ledger (WORM) */}
      {tab === 'audit' && (
        <section className="panel table">
          <h2>Immutable Audit Ledger <small>({auditData.total} events recorded)</small></h2>
          <div className="table-head" style={{ gridTemplateColumns: '1.2fr 1.2fr 1.2fr 1fr 2fr' }}>
            <span>Timestamp</span>
            <span>Actor</span>
            <span>Action</span>
            <span>Target</span>
            <span>Details / Diff</span>
          </div>

          {auditData.items.map((log) => (
            <div className="table-row" key={log.id} style={{ gridTemplateColumns: '1.2fr 1.2fr 1.2fr 1fr 2fr' }}>
              <small>{new Date(log.created_at).toLocaleString()}</small>
              <b>{log.actor_name} <small>IP: {log.ip_address || '—'}</small></b>
              <span><label className="blue" style={{ fontSize: 11 }}>{log.action}</label></span>
              <small>{log.target_type} #{log.target_id || '—'}</small>
              <code style={{ fontSize: 11, background: '#f8fafc', padding: '4px 6px', borderRadius: 4, overflowX: 'auto' }}>
                {log.details || '—'}
              </code>
            </div>
          ))}
          {!auditData.items.length && <p className="empty">No audit entries logged yet.</p>}
        </section>
      )}
    </AppShell>
  );
}
