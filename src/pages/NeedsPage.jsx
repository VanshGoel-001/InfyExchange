import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner } from '../components/Ui';
import { NeedCard } from '../components/Cards';
import { SkeletonCard } from '../components/ErrorBoundary';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import { applyClientFilters } from '../utils/filters';
import { CATEGORIES, NEED_TYPES } from '../utils/labels';

const emptyFilters = { search: '', category: '', need_type: '', location: '' };

export default function NeedsPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { token, user, loading: authLoading } = useAuth();
  const mine = params.get('scope') === 'mine';
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [applied, setApplied] = useState(false);

  const load = async (nextFilters = filters) => {
    setLoading(true);
    try {
      setError('');
      const query = Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value));
      const data = mine ? await api.myNeeds(token) : await api.needs({ limit: 100, ...query });
      const filtered = mine && Object.keys(query).length ? applyClientFilters(data, query) : data;
      setItems(filtered);
      setApplied(Object.keys(query).length > 0);
    } catch (requestError) {
      setItems([]);
      setError(requestError.message);
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
          title={mine ? 'My requests' : 'Community requests'}
          subtitle={
            mine
              ? 'Things you have asked the community for.'
              : 'See what other trainees are looking for. Have one to spare? Post it as an item.'
          }
          kind="need"
          action={mine ? 'See all requests' : 'Post a request'}
          to={mine ? '/needs' : '/needs/new'}
        />

        <form className="need-filters" onSubmit={apply}>
          <input
            aria-label="Search requests"
            value={filters.search}
            onChange={(event) => setField('search', event.target.value)}
            placeholder="Search requests"
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
            Showing only your requests. <Link to="/needs">See everyone’s requests</Link>
          </p>
        )}

        <div className="needs-body">
          <section>
            <h2>
              {loading ? 'Loading…' : `${items.length} ${items.length === 1 ? 'request' : 'requests'}${applied ? ' match your filters' : ''}`}
            </h2>

            {loading ? (
              <div className="grid needs-grid">
                {[...Array(6)].map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            ) : (
              <div className="grid needs-grid">
                {items.map((item, index) => (
                  <NeedCard item={item} i={index} key={item.id} />
                ))}
              </div>
            )}

            {!loading && !items.length && (
              <div className="empty-block">
                {error ? (
                  <p role="alert" className="error">{error}</p>
                ) : applied ? (
                  <>
                    <p>Nothing matches those filters.</p>
                    <button type="button" className="outline" onClick={clear}>Clear filters</button>
                  </>
                ) : (
                  <>
                    <p>{mine ? 'You have not posted any requests yet.' : 'No one has asked for anything yet.'}</p>
                    <Link className="primary" to="/needs/new">Post a request</Link>
                  </>
                )}
              </div>
            )}
          </section>

          <aside className="help-aside">
            <div className="tips">
              <h3>How requests work</h3>
              <p>A request tells everyone what you are looking for.</p>
              <p>Trainees who have it can post it as an item, and you will find it under Browse items.</p>
              <p>
                Got something someone asked for? <Link to="/listings/new">Post it as an item</Link>.
              </p>
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
