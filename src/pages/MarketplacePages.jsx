import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { CircleCheck, MapPin, Sparkles, Tag } from 'lucide-react';
import { Header } from '../components/Layout';
import { Banner, Field, Flash, FormError, Pill } from '../components/Ui';
import { ProductCard } from '../components/Cards';
import Gallery from '../components/Gallery';
import { SkeletonCard } from '../components/ErrorBoundary';
import { api, safe } from '../services/api';
import { useLoad } from '../hooks/useLoad';
import { InlineError, SectionBoundary, SkeletonList } from '../components/Section';
import { currentPath } from '../utils/redirect';
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

function Filters({ filters, setFilters, apply, clear, areaLoad }) {
  const areas = areaLoad.data;
  const change = (key, value) => setFilters((f) => ({ ...f, [key]: value }));
  const priceRangeWrong =
    filters.min_price !== '' && filters.max_price !== '' && Number(filters.min_price) > Number(filters.max_price);
  const area = areas?.find((a) => String(a.id) === String(filters.pickup_area_id));
  const blockWrong =
    filters.block_no !== '' && (Number(filters.block_no) < LIMITS.block[0] || Number(filters.block_no) > LIMITS.block[1]);

  return (
    <form
      className="filters"
      onSubmit={(e) => {
        e.preventDefault();
        if (!priceRangeWrong && !blockWrong) apply();
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
        <input value={filters.search} onChange={(e) => change('search', e.target.value)} placeholder="Search by listing name" />
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
        Pickup area
        <select
          value={filters.pickup_area_id}
          disabled={!areas}
          onChange={(e) => setFilters((f) => ({ ...f, pickup_area_id: e.target.value, block_no: '' }))}
        >
          <option value="">{areas || areaLoad.status === 'ready' ? 'Any area' : 'Unavailable'}</option>
          {areas?.map((x) => (
            <option key={x.id} value={x.id}>{x.name}</option>
          ))}
        </select>
      </label>
      {areaLoad.status === 'failed' && !areas && <InlineError error={areaLoad.error} context="generic" onRetry={areaLoad.reload} />}

      {area?.has_blocks && (
        <label>
          Block no.
          <input
            inputMode="numeric"
            value={filters.block_no}
            onChange={(e) => change('block_no', e.target.value.replace(/\D/g, '').slice(0, 3))}
            placeholder="Optional, 1 to 100"
          />
          {blockWrong && <small className="field-error" role="alert">Block number must be between 1 and 100.</small>}
        </label>
      )}

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

      <button type="submit" className="primary" disabled={priceRangeWrong || blockWrong}>
        Show results
      </button>
    </form>
  );
}

export function ListingsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { token, user, loading: authLoading } = useAuth();
  // null until the first real answer: an empty list is a real answer, a failed request is not.
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState(null);
  const areaLoad = useLoad(() => api.pickupAreas(), []);

  const mine = params.get('scope') === 'mine';
  const keys = ['search', 'category', 'listing_type', 'condition', 'pickup_area_id', 'block_no', 'min_price', 'max_price'];
  const initial = Object.fromEntries(keys.map((k) => [k, params.get(k) || '']));
  const [filters, setFilters] = useState(initial);

  // Only the newest request may update the screen: a slow answer to an earlier search must not overwrite it.
  const latest = useRef(0);

  const load = async (query) => {
    const ticket = ++latest.current;
    setLoading(true);
    const clean = Object.fromEntries(Object.entries(query).filter(([key, value]) => key !== 'scope' && value !== ''));
    const result = await safe(mine ? api.myListings(token) : api.listings({ limit: 100, ...clean }));
    if (ticket !== latest.current || result.aborted) return;
    setLoading(false);
    if (!result.ok) {
      // Keep the previous results on screen and say so in one line; never turn a failure into "no listings".
      setFailure(result.error);
      return;
    }
    setFailure(null);
    setItems(mine && Object.keys(clean).length ? applyClientFilters(result.data, clean) : result.data);
  };

  useEffect(() => {
    if (mine && !authLoading && !user) {
      navigate(`/login?next=${encodeURIComponent(currentPath())}`, { replace: true });
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
        <SectionBoundary name="filters" context="generic"><Filters filters={filters} setFilters={setFilters} apply={apply} clear={clear} areaLoad={areaLoad} /></SectionBoundary>
        <main>
          <Banner
            title={mine ? 'My listings' : 'Browse listings'}
            subtitle={
              mine
                ? 'Listings you have posted on InfyExchange.'
                : 'Find sports gear from fellow trainees: buy it, rent it, borrow it, or get it free.'
            }
          />
          {mine && (
            <p className="scope-note">
              Showing only listings you posted. <Link to="/listings">See everything</Link>
            </p>
          )}

          <div className="listing-toolbar">
            <h2>
              {items === null ? (loading ? 'Loading…' : 'Listings') : `${items.length} ${items.length === 1 ? 'listing' : 'listings'}${filtered ? ' match your filters' : ''}`}
            </h2>
          </div>

          <SectionBoundary name="listings list" context="listings">
            {failure && <InlineError error={failure} context={filters.search ? 'search' : 'listings'} onRetry={() => load(Object.fromEntries(params.entries()))} />}

            {items === null && loading && (
              <div className="grid listing-grid">
                {[...Array(6)].map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            )}

            {items !== null && (
              <div className="grid listing-grid">
                {items.map((p, i) => (
                  <ProductCard item={p} i={i} key={p.id} />
                ))}
              </div>
            )}
          </SectionBoundary>

          {items !== null && !loading && !items.length && !failure && (
            <div className="empty-block">
              {filtered ? (
                <>
                  <p>Nothing matches those filters.</p>
                  <button type="button" className="outline" onClick={clear}>Clear filters</button>
                </>
              ) : (
                <>
                  <p>{mine ? 'You have not posted anything yet.' : 'No listings have been posted yet.'}</p>
                  <Link className="primary" to="/listings/new">Post a listing</Link>
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
  const form = useForm({ message: '' }, validateInterest, ['message'], { context: 'enquiry' });
  const { bind, values, error } = form;

  const send = form.handleSubmit(async () => {
    await api.createInterest(id, { message: values.message.trim() }, token, form.idempotencyKey());
    setSent(true);
  });

  if (user?.id === item.owner_id) {
    return (
      <div className="interest">
        <h2>This is your listing</h2>
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
        <Link className="primary" to="/listings">Browse other listings</Link>
      </div>
    );
  }

  if (!token) {
    return (
      <div className="interest">
        <h2>Interested in this listing?</h2>
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
        <p>We need your phone number and role before you can enquire about listings.</p>
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
      <h2>Interested in this listing?</h2>
      <Field label="Message to the owner, optional" error={error('message')} hint={`${values.message.trim().length} / ${LIMITS.message[1]}`}>
        <textarea {...bind('message')} maxLength={LIMITS.message[1]} placeholder="e.g. Is it still available? Can I pick it up this evening?" />
      </Field>
      <FormError failure={form.failure} onRetry={form.resubmit}>{form.formError}</FormError>
      <button className="primary" disabled={form.busy} aria-busy={form.busy}>
        {form.busy ? 'Sending…' : 'Send enquiry'}
      </button>
    </form>
  );
}

// Keeps the writer's line breaks and shows four lines until "Read more" is pressed.
function Description({ text }) {
  const body = useRef(null);
  const [open, setOpen] = useState(false);
  const [long, setLong] = useState(false);

  useLayoutEffect(() => {
    const check = () => {
      const el = body.current;
      if (el && !open) setLong(el.scrollHeight > el.clientHeight + 1);
    };
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, [text, open]);

  return (
    <section className="panel description">
      <h2>Description</h2>
      <p ref={body} className={open ? '' : 'clamped'}>{text}</p>
      {(long || open) && (
        <button type="button" className="read-more" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? 'Show less' : 'Read more'}
        </button>
      )}
    </section>
  );
}

export function DetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  // Three different answers: still loading, the server says there is no such listing, or the request failed.
  const load = useLoad(() => api.listing(id), [id]);
  const item = load.status === 'ready' ? load.data : null;

  if (load.status === 'loading') {
    return (
      <>
        <Header />
        <main className="wide detail">
          <SkeletonList rows={3} />
        </main>
      </>
    );
  }

  if (!item) {
    const gone = load.error?.kind === 'notfound';
    return (
      <>
        <Header />
        <main className="wide detail">
          {gone ? (
            <p role="alert" className="error">This listing could not be found. It may have been removed.</p>
          ) : (
            <InlineError error={load.error} context="listings" onRetry={load.reload} />
          )}
          <button className="primary" onClick={() => navigate('/listings')}>
            Back to all listings
          </button>
        </main>
      </>
    );
  }

  const specs = [
    [Tag, 'Category', labelOf(CATEGORIES, item.category)],
    [Sparkles, 'Condition', labelOf(CONDITIONS, item.condition)],
    [MapPin, 'Pickup area', item.location],
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
          <SectionBoundary name="photos" context="generic"><Gallery images={item.images} title={item.title} category={item.category} /></SectionBoundary>

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

            <SectionBoundary name="enquiry panel" context="enquiry"><InterestPanel item={item} id={id} /></SectionBoundary>
          </aside>

          <SectionBoundary name="description" context="generic"><Description text={item.description} /></SectionBoundary>
        </div>
      </main>
    </>
  );
}
