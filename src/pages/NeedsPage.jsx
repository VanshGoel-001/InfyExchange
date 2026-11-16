import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner } from '../components/Ui';
import { NeedCard } from '../components/Cards';
import { InlineError, SectionBoundary } from '../components/Section';
import { SkeletonCard } from '../components/ErrorBoundary';
import { useAuth } from '../context/AuthContext';
import { api, safe } from '../services/api';
import { applyClientFilters } from '../utils/filters';
import { CATEGORIES, NEED_TYPES } from '../utils/labels';

const emptyFilters = { search: '', category: '', need_type: '', location: '' };

export default function NeedsPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { token, user, loading: authLoading } = useAuth();
  const mine = params.get('scope') === 'mine';
  // null until the first real answer: an empty list is a real answer, a failed request is not.
  const [items, setItems] = useState(null);
  const [filters, setFilters] = useState(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState(null);
  const [applied, setApplied] = useState(false);

  // Only the newest request may update the screen: a slow answer to an earlier search must not overwrite it.
  const latest = useRef(0);

  const load = async (nextFilters = filters) => {
    const ticket = ++latest.current;
    setLoading(true);
    const query = Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value));
    const result = await safe(mine ? api.myNeeds(token) : api.needs({ limit: 100, ...query }));
    if (ticket !== latest.current || result.aborted) return;
    setLoading(false);
    if (!result.ok) {
      // Keep whatever was on screen and say so in one line; never turn a failure into "no needs".
      setFailure(result.error);
      return;
    }
    setFailure(null);
    setItems(mine && Object.keys(query).length ? applyClientFilters(result.data, query) : result.data);
    setApplied(Object.keys(query).length > 0);
  };

  useEffect(() => {
    if (mine && !authLoading && !user) {
      navigate('/login', { replace: true });
      return;
    }
    if (mine && authLoading) return;
    load(emptyFilters);
  }, [mine, token, user, authLoading]);

  const setField = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const apply = (event) => {
    event.preventDefault();
    load(filters);
  };
  const clear = () => {
    setFilters(emptyFilters);
    load(emptyFilters);
  };

  return (
    <>
      <Header />
      <main className="wide catalogue-page">
        <Banner
          title={mine ? 'My needs' : 'Community needs'}
          subtitle={
            mine
              ? 'Things you have asked the community for.'
              : 'See what other trainees are looking for. Have one to spare? Post it as an item.'
          }
          kind="need"
          action={mine ? 'See all needs' : 'Post a need'}
          to={mine ? '/needs' : '/needs/new'}
        />

        <form className="need-filters" onSubmit={apply}>
          <input
            aria-label="Search needs"
            value={filters.search}
            onChange={(event) => setField('search', event.target.value)}
            placeholder="Search needs"
          />
          <select aria-label="Category" value={filters.category} onChange={(event) => setField('category', event.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <select aria-label="Looking to" value={filters.need_type} onChange={(event) => setField('need_type', event.target.value)}>
            <option value="">Buy, rent or borrow</option>
            {NEED_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <input
            aria-label="Location"
            value={filters.location}
            onChange={(event) => setField('location', event.target.value)}
            placeholder="Location, e.g. ECC"
          />
          <button className="primary" type="submit">
            Show results
          </button>
        </form>

        {mine && (
          <p className="scope-note">
            Showing only your needs. <Link to="/needs">See everyone’s needs</Link>
          </p>
        )}

        <div className="needs-body">
          <section>
            <h2>
              {items === null ? (loading ? 'Loading…' : 'Needs') : `${items.length} ${items.length === 1 ? 'need' : 'needs'}${applied ? ' match your filters' : ''}`}
            </h2>

            <SectionBoundary name="needs list" context="needs">
              {failure && <InlineError error={failure} context={filters.search ? 'search' : 'needs'} onRetry={() => load(filters)} />}

              {items === null && loading && (
                <div className="grid needs-grid">
                  {[...Array(6)].map((_, i) => (
                    <SkeletonCard key={i} />
                  ))}
                </div>
              )}

              {items !== null && (
                <div className="grid needs-grid">
                  {items.map((item, index) => (
                    <NeedCard item={item} i={index} key={item.id} />
                  ))}
                </div>
              )}
            </SectionBoundary>

            {items !== null && !loading && !items.length && !failure && (
              <div className="empty-block">
                {applied ? (
                  <>
                    <p>Nothing matches those filters.</p>
                    <button type="button" className="outline" onClick={clear}>Clear filters</button>
                  </>
                ) : (
                  <>
                    <p>{mine ? 'You have not posted any needs yet.' : 'No one has asked for anything yet.'}</p>
                    <Link className="primary" to="/needs/new">Post a need</Link>
                  </>
                )}
              </div>
            )}
          </section>

          <aside className="help-aside">
            <div className="tips">
              <h3>How needs work</h3>
              <p>A request tells everyone what you are looking for.</p>
              <p>Trainees who have it can post it as a listing, and you will find it under Browse listings.</p>
              <p>
                Got something someone asked for? <Link to="/listings/new">Post it as a listing</Link>.
              </p>
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
