import {useEffect, useState} from 'react';
import {Link, useNavigate, useSearchParams} from 'react-router-dom';
import {Header} from '../components/Layout';
import {Banner} from '../components/Ui';
import {NeedCard} from '../components/Cards';
import {useAuth} from '../context/AuthContext';
import {api} from '../services/api';

const cats = ['BADMINTON', 'TABLE_TENNIS', 'POOL_SNOOKER', 'SQUASH', 'TENNIS', 'CRICKET', 'FOOTBALL', 'BASKETBALL', 'OTHER'];
const emptyFilters = {search: '', category: '', need_type: '', location: ''};

export default function NeedsPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const {token, user, loading} = useAuth();
  const mine = params.get('scope') === 'mine';
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState(emptyFilters);
  const [error, setError] = useState('');

  const load = async (nextFilters = filters) => {
    try {
      setError('');
      const query = Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value));
      const data = mine ? await api.myNeeds(token) : await api.needs({limit: 100, ...query});
      const filtered = mine && Object.keys(query).length
        ? data.filter(item => Object.entries(query).every(([key, value]) => String(item[key] || '').toLowerCase().includes(value.toLowerCase())))
        : data;
      setItems(filtered);
    } catch (requestError) {
      setItems([]);
      setError(requestError.message);
    }
  };

  useEffect(() => {
    if (mine && !loading && !user) {
      navigate('/login', {replace: true});
      return;
    }
    if (mine && loading) return;
    load(emptyFilters);
  }, [mine, token, user, loading]);

  const set = (key, value) => setFilters(current => ({...current, [key]: value}));
  const apply = event => {event.preventDefault(); load(filters);};

  return <><Header/><main className="wide catalogue-page">
    <Banner title={mine ? 'My Needs' : 'Community Needs'} subtitle={mine ? 'Requests you have posted for the community.' : 'See what other trainees are looking for. Find someone who can help.'} kind="need" action={mine ? 'Browse Needs' : 'Post a Need'} to={mine ? '/needs' : '/needs/new'}/>
    <form className="need-filters" onSubmit={apply}>
      <input value={filters.search} onChange={event => set('search', event.target.value)} placeholder="Search needs"/>
      <select value={filters.category} onChange={event => set('category', event.target.value)}><option value="">All Categories</option>{cats.map(value => <option key={value}>{value}</option>)}</select>
      <select value={filters.need_type} onChange={event => set('need_type', event.target.value)}><option value="">All Requests</option>{['BUY', 'RENT', 'BORROW'].map(value => <option key={value}>{value}</option>)}</select>
      <input value={filters.location} onChange={event => set('location', event.target.value)} placeholder="Location"/>
      <button className="primary" type="submit">Apply filters</button>
    </form>
    {mine && <p className="scope-note">Showing requests posted by you. <Link to="/needs">Browse all community needs</Link></p>}
    <div className="needs-body"><section><h2>{items.length} {mine ? 'My Needs' : 'Needs Found'}</h2><div className="grid needs-grid">{items.map((item, index) => <NeedCard item={item} i={index} key={item.id}/>)}</div>{!items.length && <p className="empty">{error || (mine ? 'You have not posted any needs yet.' : 'No active needs found.')}</p>}</section><aside className="help-aside"><div className="tips"><h3>💡 How it works?</h3><p>Browse needs posted by trainees.</p><p>Contact the requester using your preferred channel.</p></div></aside></div>
  </main></>;
}
