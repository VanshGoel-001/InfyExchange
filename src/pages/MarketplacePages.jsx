import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftRight, CircleCheck, IndianRupee, MapPin, Sparkles, Tag } from 'lucide-react';
import { Header } from '../components/Layout';
import { Banner, Field, Flash, FormError, Pill } from '../components/Ui';
import { ProductCard } from '../components/Cards';
import { SkeletonCard } from '../components/ErrorBoundary';
import { api } from '../services/api';
import { applyClientFilters } from '../utils/filters';
import {
  CATEGORIES,
  CONDITIONS,
  LISTING_STATUSES,
  LISTING_TYPES,
  ROLES,
  formatDate,
  formatPrice,
  initials,
  labelOf,
  toneOf,
} from '../utils/labels';
import { LIMITS, validateInterest } from '../utils/validate';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';

function Filters({ filters, setFilters, apply, clear }) {
  const change = (key, value) => setFilters((f) => ({ ...f, [key]: value }));
  const priceRangeWrong =
    filters.min_price !== '' && filters.max_price !== '' && Number(filters.min_price) > Number(filters.max_price);

  return (
    <form
      className="filters"
      onSubmit={(e) => {
        e.preventDefault();
        if (!priceRangeWrong) apply();
      }}
    >
      <div className="filters-head">
        <b>Filters</b>
        <button type="button" className="filter-clear" onClick={clear}>
          Clear all
        </button>
      </div>

      <label>
        Search
        <input value={filters.search} onChange={(e) => change('search', e.target.value)} placeholder="Search by item name" />
      </label>

      <label>
        Category
        <select value={filters.category} onChange={(e) => change('category', e.target.value)}>
          <option value="">All categories</option>
          {CATEGORIES.map((x) => (
            <option key={x.value} value={x.value}>{x.label}</option>
          ))}
        </select>
      </label>

      <label>
        What is on offer
        <select value={filters.listing_type} onChange={(e) => change('listing_type', e.target.value)}>
          <option value="">Anything</option>
          {LISTING_TYPES.map((x) => (
            <option key={x.value} value={x.value}>{x.label}</option>
          ))}
        </select>
      </label>

      <label>
        Condition
        <select value={filters.condition} onChange={(e) => change('condition', e.target.value)}>
          <option value="">Any condition</option>
          {CONDITIONS.map((x) => (
            <option key={x.value} value={x.value}>{x.label}</option>
          ))}
        </select>
      </label>

      <label>
        Location
        <input value={filters.location} onChange={(e) => change('location', e.target.value)} placeholder="e.g. ECC, Food Court" />
      </label>

      <fieldset className="price-range">
        <legend>Price (₹)</legend>
        <div className="inline">
          <input
            type="number"
            min="0"
            inputMode="numeric"
            aria-label="Minimum price"
            value={filters.min_price}
            onChange={(e) => change('min_price', e.target.value)}
            placeholder="From"
          />
          <input
            type="number"
            min="0"
            inputMode="numeric"
            aria-label="Maximum price"
            value={filters.max_price}
            onChange={(e) => change('max_price', e.target.value)}
            placeholder="To"
          />
        </div>
        {priceRangeWrong && <small className="field-error" role="alert">“From” must not be higher than “To”.</small>}
      </fieldset>

      <button type="submit" className="primary" disabled={priceRangeWrong}>
        Show results
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

  // Only the newest request may update the screen: a slow answer to an earlier search must not overwrite it.
  const latest = useRef(0);

  const load = async (query) => {
    const ticket = ++latest.current;
    setLoading(true);
    try {
      setError('');
      const clean = Object.fromEntries(Object.entries(query).filter(([key, value]) => key !== 'scope' && value !== ''));
      const data = mine ? await api.myListings(token) : await api.listings({ limit: 100, ...clean });
      const filtered = mine && Object.keys(clean).length ? applyClientFilters(data, clean) : data;
      if (ticket === latest.current) setItems(filtered);
    } catch (err) {
      if (ticket !== latest.current) return;
      setItems([]);
      setError(err.message);
    } finally {
      if (ticket === latest.current) setLoading(false);
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

  const filtered = Object.keys(Object.fromEntries(params.entries())).some((key) => key !== 'scope');

  return (
    <>
      <Header />
      <div className="page-layout catalogue-layout">
        <Filters filters={filters} setFilters={setFilters} apply={apply} clear={clear} />
        <main>
          <Banner
            title={mine ? 'My items' : 'Browse items'}
            subtitle={
              mine
                ? 'Items you have posted on InfyExchange.'
                : 'Find sports gear from fellow trainees: buy it, rent it, borrow it, or get it free.'
            }
          />
          {mine && (
            <p className="scope-note">
              Showing only items you posted. <Link to="/listings">See everything</Link>
            </p>
          )}

          <div className="listing-toolbar">
            <h2>
              {loading ? 'Loading…' : `${items.length} ${items.length === 1 ? 'item' : 'items'}${filtered ? ' match your filters' : ''}`}
            </h2>
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
            <div className="empty-block">
              {error ? (
                <p role="alert" className="error">{error}</p>
              ) : filtered ? (
                <>
                  <p>Nothing matches those filters.</p>
                  <button type="button" className="outline" onClick={clear}>Clear filters</button>
                </>
              ) : (
                <>
                  <p>{mine ? 'You have not posted anything yet.' : 'No items have been posted yet.'}</p>
                  <Link className="primary" to="/listings/new">Post an item</Link>
                </>
              )}
            </div>
          )}
        </main>
      </div>
    </>
  );
}

function InterestPanel({ item, id }) {
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const [sent, setSent] = useState(false);
  const form = useForm({ message: '' }, validateInterest, ['message']);
  const { bind, values, error } = form;

  const send = form.handleSubmit(async () => {
    await api.createInterest(id, { message: values.message.trim() }, token);
    setSent(true);
  });

  if (user?.id === item.owner_id) {
    return (
      <div className="interest">
        <h2>This is your item</h2>
        <p>Enquiries from other trainees appear under “Enquiries”.</p>
        <Link className="primary" to="/activity">See enquiries</Link>
      </div>
    );
  }

  if (item.status !== 'ACTIVE') {
    return (
      <div className="interest">
        <h2>No longer available</h2>
        <p>This item is marked as {labelOf(LISTING_STATUSES, item.status).toLowerCase()}.</p>
        <Link className="primary" to="/listings">Browse other items</Link>
      </div>
    );
  }

  if (!token) {
    return (
      <div className="interest">
        <h2>Interested in this item?</h2>
        <p>Log in to send {item.owner_name?.split(' ')[0] || 'the owner'} an enquiry. It only takes a moment.</p>
        <button className="primary" onClick={() => navigate('/login')}>Log in to continue</button>
        <p className="aside-link">New here? <Link to="/register">Create an account</Link></p>
      </div>
    );
  }

  if (user && !user.profile_complete) {
    return (
      <div className="interest">
        <h2>Finish your profile first</h2>
        <p>We need your phone number and role before you can enquire about items.</p>
        <Link className="primary" to="/complete-profile">Finish profile</Link>
      </div>
    );
  }

  if (sent) {
    return (
      <div className="interest">
        <h2>Enquiry sent</h2>
        <p>
          {item.owner_name?.split(' ')[0] || 'The owner'} will see it under “Enquiries”. If they accept,
          you can chat and see their contact details there.
        </p>
        <Link className="outline" to="/activity">See my enquiries</Link>
      </div>
    );
  }

  return (
    <form className="interest" onSubmit={send} noValidate>
      <h2>Interested in this item?</h2>
      <Field label="Message to the owner, optional" error={error('message')} hint={`${values.message.trim().length} / ${LIMITS.message[1]}`}>
        <textarea {...bind('message')} maxLength={LIMITS.message[1]} placeholder="e.g. Is it still available? Can I pick it up this evening?" />
      </Field>
      <FormError>{form.formError}</FormError>
      <button className="primary" disabled={form.busy} aria-busy={form.busy}>
        {form.busy ? 'Sending…' : 'Send enquiry'}
      </button>
    </form>
  );
}

export function DetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let current = true; // ignore the answer if the person has moved to another item meanwhile
    setLoading(true);
    setNotice('');
    api
      .listing(id)
      .then((data) => current && setItem(data))
      .catch((e) => current && setNotice(e.message))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [id]);

  if (loading) {
    return (
      <>
        <Header />
        <main className="wide detail">
          <p className="page-status">Loading item…</p>
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
            {notice || 'This item could not be found. It may have been removed.'}
          </p>
          <button className="primary" onClick={() => navigate('/listings')}>
            Back to all items
          </button>
        </main>
      </>
    );
  }

  const specs = [
    [Tag, 'Category', labelOf(CATEGORIES, item.category)],
    [ArrowLeftRight, 'On offer as', labelOf(LISTING_TYPES, item.listing_type)],
    [Sparkles, 'Condition', labelOf(CONDITIONS, item.condition)],
    [IndianRupee, 'Price', formatPrice(item.price, item.price_unit)],
    [MapPin, 'Pickup location', item.location],
    [CircleCheck, 'Availability', labelOf(LISTING_STATUSES, item.status)],
  ];

  return (
    <>
      <Header />
      <main className="wide detail">
        <Flash />
        <button className="back-link" onClick={() => navigate(-1)}>
          ← Back
        </button>

        <div className="detail-grid">
          <section>
            <div className="detail-picture">
              {item.images?.[0]?.image_url ? (
                <img src={item.images[0].image_url} alt={item.title} />
              ) : (
                <span className="no-image">No photo added</span>
              )}
            </div>
            <div className="panel description">
              <h2>Description</h2>
              <p>{item.description}</p>
            </div>
          </section>

          <section className="item-info">
            <Pill tone={toneOf(LISTING_TYPES, item.listing_type)}>{labelOf(LISTING_TYPES, item.listing_type)}</Pill>
            <h1>{item.title}</h1>
            <strong>{formatPrice(item.price, item.price_unit)}</strong>
            <p>Posted {formatDate(item.created_at)}</p>
            <div className="specs">
              {specs.map(([Icon, name, value]) => (
                <span key={name}>
                  <Icon aria-hidden="true" />
                  <b>
                    {name}
                    <small>{value}</small>
                  </b>
                </span>
              ))}
            </div>
          </section>

          <aside>
            <div className="panel posted">
              <h3>Posted by</h3>
              <div className="large-avatar tiny">{initials(item.owner_name)}</div>
              <b>
                {item.owner_name}
                <small>{labelOf(ROLES, item.owner_role)}</small>
              </b>
            </div>

            <InterestPanel item={item} id={id} />
          </aside>
        </div>
      </main>
    </>
  );
}
