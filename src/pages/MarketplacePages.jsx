import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner } from '../components/Ui';
import { ProductCard } from '../components/Cards';
import { SkeletonCard } from '../components/ErrorBoundary';
import { api } from '../services/api';
import { applyClientFilters } from '../utils/filters';
import { useAuth } from '../context/AuthContext';

const CATEGORIES = [
  'BADMINTON',
  'TABLE_TENNIS',
  'POOL_SNOOKER',
  'SQUASH',
  'TENNIS',
  'CRICKET',
  'FOOTBALL',
  'BASKETBALL',
  'OTHER',
];

const LISTING_TYPES = ['SELL', 'RENT', 'LEND', 'GIVEAWAY'];
const CONDITIONS = ['NEW', 'LIKE_NEW', 'GOOD', 'FAIR', 'POOR'];

function Filters({ filters, setFilters, apply, clear }) {
  const change = (key, value) => setFilters((f) => ({ ...f, [key]: value }));

  return (
    <form
      className="filters"
      onSubmit={(e) => {
        e.preventDefault();
        apply();
      }}
    >
      <b>⚱ Filters</b>
      <button type="button" className="filter-clear" onClick={clear}>
        Clear All
      </button>

      <label>
        Search
        <input
          value={filters.search}
          onChange={(e) => change('search', e.target.value)}
          placeholder="Search items by name"
        />
      </label>

      <label>
        Category
        <select value={filters.category} onChange={(e) => change('category', e.target.value)}>
          <option value="">All Categories</option>
          {CATEGORIES.map((x) => (
            <option key={x} value={x}>
              {x.replace('_', ' ')}
            </option>
          ))}
        </select>
      </label>

      <label>
        Listing Type
        <select value={filters.listing_type} onChange={(e) => change('listing_type', e.target.value)}>
          <option value="">All Types</option>
          {LISTING_TYPES.map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </select>
      </label>

      <label>
        Condition
        <select value={filters.condition} onChange={(e) => change('condition', e.target.value)}>
          <option value="">All Conditions</option>
          {CONDITIONS.map((x) => (
            <option key={x} value={x}>
              {x.replace('_', ' ')}
            </option>
          ))}
        </select>
      </label>

      <label>
        Location
        <input
          value={filters.location}
          onChange={(e) => change('location', e.target.value)}
          placeholder="e.g. ECC, FC"
        />
      </label>

      <div className="inline">
        <input
          type="number"
          min="0"
          value={filters.min_price}
          onChange={(e) => change('min_price', e.target.value)}
          placeholder="Min ₹"
        />
        <input
          type="number"
          min="0"
          value={filters.max_price}
          onChange={(e) => change('max_price', e.target.value)}
          placeholder="Max ₹"
        />
      </div>

      <button type="submit" className="primary">
        Apply Filters
      </button>
    </form>
  );
}

export function ListingsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { token, user, loading: authLoading } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const mine = params.get('scope') === 'mine';
  const keys = ['search', 'category', 'listing_type', 'condition', 'location', 'min_price', 'max_price'];
  const initial = Object.fromEntries(keys.map((k) => [k, params.get(k) || '']));
  const [filters, setFilters] = useState(initial);

  const load = async (query) => {
    setLoading(true);
    try {
      setError('');
      const clean = Object.fromEntries(Object.entries(query).filter(([key, value]) => key !== 'scope' && value !== ''));
      const data = mine ? await api.myListings(token) : await api.listings({ limit: 100, ...clean });
      const filtered = mine && Object.keys(clean).length ? applyClientFilters(data, clean) : data;
      setItems(filtered);
    } catch (err) {
      setItems([]);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (mine && !authLoading && !user) {
      navigate('/login', { replace: true });
      return;
    }
    if (mine && authLoading) return;

    const q = Object.fromEntries(params.entries());
    const next = { ...Object.fromEntries(keys.map((k) => [k, ''])), ...q };
    delete next.scope;
    setFilters(next);
    load(q);
  }, [params.toString(), mine, token, user, authLoading]);

  const apply = () => {
    setParams(Object.fromEntries(Object.entries({ ...filters, ...(mine ? { scope: 'mine' } : {}) }).filter(([, v]) => v !== '')));
  };

  const clear = () => {
    setFilters(Object.fromEntries(keys.map((k) => [k, ''])));
    setParams(mine ? { scope: 'mine' } : {});
  };

  return (
    <>
      <Header />
      <div className="page-layout catalogue-layout">
        <Filters filters={filters} setFilters={setFilters} apply={apply} clear={clear} />
        <main>
          <Banner
            title={mine ? 'My Listings' : 'Browse Listings'}
            subtitle={
              mine
                ? 'Items you have posted to InfyExchange.'
                : 'Find items from fellow trainees. Buy, rent, lend or give within our community.'
            }
          />
          {mine && (
            <p className="scope-note">
              Showing items posted by you. <Link to="/listings">Browse all community listings</Link>
            </p>
          )}

          <div className="listing-toolbar">
            <h2>{items.length} {mine ? 'My Listings' : 'Listings Found'}</h2>
          </div>

          {loading ? (
            <div className="grid listing-grid">
              {[...Array(6)].map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          ) : (
            <div className="grid listing-grid">
              {items.map((p, i) => (
                <ProductCard item={p} i={i} key={p.id} />
              ))}
            </div>
          )}

          {!loading && !items.length && (
            <p className="empty">
              {error || (mine ? 'You have not posted any listings yet.' : 'No active listings found matching your criteria.')}
            </p>
          )}
        </main>
      </div>
    </>
  );
}

export function DetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setLoading(true);
    api
      .listing(id)
      .then(setItem)
      .catch((e) => setNotice(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <>
        <Header />
        <main className="wide detail">
          <p className="page-status">Loading item details…</p>
        </main>
      </>
    );
  }

  if (!item) {
    return (
      <>
        <Header />
        <main className="wide detail">
          <p role="alert" className="error">
            {notice || 'Listing not found or no longer active.'}
          </p>
          <button className="primary" onClick={() => navigate('/listings')}>
            ← Back to listings
          </button>
        </main>
      </>
    );
  }

  const own = user?.id === item.owner_id;

  const send = async () => {
    if (!token) return navigate('/login');
    setSubmitting(true);
    try {
      await api.createInterest(id, { message: message.trim() }, token);
      setNotice('Interest sent to the owner! You will be notified when they respond.');
      setMessage('');
    } catch (e) {
      setNotice(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const specs = [
    ['🏸', 'Category', item.category],
    ['🏷️', 'Type', item.listing_type],
    ['⚙', 'Condition', item.condition],
    ['₹', 'Price', item.price > 0 ? `₹${item.price}${item.price_unit ? `/${item.price_unit}` : ''}` : 'Free'],
    ['⌖', 'Location', item.location],
    ['◷', 'Status', item.status],
  ];

  return (
    <>
      <Header />
      <main className="wide detail">
        <button className="back-link" onClick={() => navigate(-1)}>
          ← Back to listings
        </button>
        <p className="crumb">
          Home › Listings › {item.title}
        </p>

        <div className="detail-grid">
          <section>
            <div className="detail-picture">
              {item.images?.[0]?.image_url ? (
                <img src={item.images[0].image_url} alt={item.title} />
              ) : (
                <span className="no-image">No image uploaded</span>
              )}
            </div>
            <div className="panel description">
              <h2>▤ Description</h2>
              <p>{item.description}</p>
            </div>
          </section>

          <section className="item-info">
            <label className="blue">{item.listing_type}</label>
            <h1>{item.title}</h1>
            <strong>{item.price > 0 ? `₹${item.price}` : 'Free'}</strong>
            <p>Posted {new Date(item.created_at).toLocaleDateString()}</p>
            <div className="specs">
              {specs.map((x) => (
                <span key={x[1]}>
                  {x[0]}
                  <b>
                    {x[1]}
                    <small>{String(x[2]).replaceAll('_', ' ')}</small>
                  </b>
                </span>
              ))}
            </div>
          </section>

          <aside>
            <div className="panel posted">
              <h3>Posted by</h3>
              <div className="large-avatar tiny">{item.owner_name?.slice(0, 2).toUpperCase()}</div>
              <b>
                {item.owner_name}
                <small>{item.owner_role}</small>
              </b>
            </div>

            {!own && (
              <div className="interest">
                <h2>Interested in this item?</h2>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Hi, I'm interested in this item. Is it still available?"
                />
                <button className="primary" disabled={submitting} onClick={send}>
                  {submitting ? 'Sending…' : token ? '⌁ I’m Interested' : 'Login to show interest'}
                </button>
                {notice && (
                  <p style={{ marginTop: 10, color: notice.includes('sent') ? '#0ba573' : '#c3283e' }}>
                    {notice}
                  </p>
                )}
              </div>
            )}
          </aside>
        </div>
      </main>
    </>
  );
}
