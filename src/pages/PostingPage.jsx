import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner, TipBox } from '../components/Ui';
import { api } from '../services/api';
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

const ITEM_CONDITIONS = ['NEW', 'LIKE_NEW', 'GOOD', 'FAIR', 'POOR'];
const LISTING_TYPES = ['SELL', 'RENT', 'LEND', 'GIVEAWAY'];
const NEED_TYPES = ['BUY', 'RENT', 'BORROW'];
const RENT_UNITS = ['day', 'week', 'month', 'hour'];

export default function PostingPage({ need = false }) {
  const navigate = useNavigate();
  const { token } = useAuth();
  const title = need ? 'Post a Need' : 'Post a Listing';

  const [form, setForm] = useState({
    title: '',
    category: 'BADMINTON',
    listing_type: 'SELL',
    need_type: 'BUY',
    price: '',
    price_unit: 'day',
    condition: 'GOOD',
    duration: '',
    budget: '',
    location: 'ECC',
    description: '',
    images: [],
  });

  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submitLock = useRef(false);
  const abortRef = useRef(null);

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (submitLock.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  const isPaid = ['SELL', 'RENT'].includes(form.listing_type);
  const isRent = form.listing_type === 'RENT';

  const validateForm = () => {
    const trimmedTitle = form.title.trim();
    if (trimmedTitle.length < 2 || trimmedTitle.length > 150) {
      throw new Error('Title must be between 2 and 150 characters.');
    }

    const trimmedLocation = form.location.trim();
    if (trimmedLocation.length < 2 || trimmedLocation.length > 100) {
      throw new Error('Location must be between 2 and 100 characters.');
    }

    const trimmedDesc = form.description.trim();
    if (trimmedDesc.length < 2 || trimmedDesc.length > 2000) {
      throw new Error('Description must be between 2 and 2000 characters.');
    }

    if (!need) {
      if (isPaid) {
        const numPrice = Number(form.price);
        if (!Number.isFinite(numPrice) || numPrice <= 0) {
          throw new Error('Please enter a valid price greater than zero.');
        }
      }
      if (form.images.length > 5) {
        throw new Error('You can upload a maximum of 5 images.');
      }
      for (const file of form.images) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
          throw new Error(`File "${file.name}" is not a valid format. Only JPEG, PNG, and WebP are supported.`);
        }
        if (file.size > 5 * 1024 * 1024) {
          throw new Error(`File "${file.name}" exceeds the 5MB size limit.`);
        }
      }
    } else {
      if (form.budget && Number(form.budget) < 0) {
        throw new Error('Budget cannot be negative.');
      }
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (submitLock.current) return;
    submitLock.current = true;
    abortRef.current = new AbortController();
    setSubmitting(true);
    setError('');

    try {
      validateForm();

      if (need) {
        await api.createNeed(
          {
            title: form.title.trim(),
            category: form.category,
            need_type: form.need_type,
            duration: form.duration.trim() || null,
            budget: Number(form.budget || 0),
            location: form.location.trim(),
            description: form.description.trim(),
          },
          token,
          abortRef.current.signal
        );
      } else {
        const formData = new FormData();
        formData.append('title', form.title.trim());
        formData.append('category', form.category);
        formData.append('listing_type', form.listing_type);
        formData.append('price', String(isPaid ? Number(form.price || 0) : 0));
        if (isRent) {
          formData.append('price_unit', form.price_unit);
        }
        formData.append('condition', form.condition);
        formData.append('location', form.location.trim());
        formData.append('description', form.description.trim());

        form.images.forEach((file) => {
          formData.append('images', file);
        });

        await api.createListing(formData, token, abortRef.current.signal);
      }

      navigate(need ? '/needs' : '/listings');
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message);
    } finally {
      submitLock.current = false;
      abortRef.current = null;
      setSubmitting(false);
    }
  };

  return (
    <>
      <Header />
      <main className="wide">
        <Banner
          title={title}
          subtitle={
            need
              ? 'Tell the community what you need. Someone might have it!'
              : 'Share something you want to sell, rent, lend or give away with fellow Infosys Mysore trainees.'
          }
          kind={need ? 'need' : 'sports'}
        />
        <div className="post-layout">
          <form className="form-card" onSubmit={submit} noValidate>
            <h2>{need ? '▤ Need Details' : 'Item Details'}</h2>

            <label className="form-field">
              Item Name *
              <input
                required
                minLength="2"
                maxLength="150"
                value={form.title}
                onChange={(e) => setField('title', e.target.value)}
                placeholder="e.g. Yonex Badminton Racket"
              />
            </label>

            <div className="two">
              <label className="form-field">
                Category *
                <select value={form.category} onChange={(e) => setField('category', e.target.value)}>
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </label>

              <label className="form-field">
                {need ? 'Looking for *' : 'Listing Type *'}
                <select
                  value={need ? form.need_type : form.listing_type}
                  onChange={(e) => setField(need ? 'need_type' : 'listing_type', e.target.value)}
                >
                  {(need ? NEED_TYPES : LISTING_TYPES).map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="two">
              <label className="form-field">
                {need ? 'Duration' : 'Price (₹)'}
                <input
                  type={need ? 'text' : 'number'}
                  min="1"
                  disabled={!need && !isPaid}
                  value={need ? form.duration : form.price}
                  onChange={(e) => setField(need ? 'duration' : 'price', e.target.value)}
                  placeholder={need ? 'e.g. 2 weeks' : isPaid ? '₹ Amount' : '0 (Free)'}
                  required={!need && isPaid}
                />
              </label>

              <label className="form-field">
                {need ? 'Budget (₹)' : isRent ? 'Duration Unit' : 'Item Condition'}
                {need ? (
                  <input
                    type="number"
                    min="0"
                    value={form.budget}
                    onChange={(e) => setField('budget', e.target.value)}
                    placeholder="Max budget"
                  />
                ) : isRent ? (
                  <select value={form.price_unit} onChange={(e) => setField('price_unit', e.target.value)}>
                    {RENT_UNITS.map((u) => (
                      <option key={u} value={u}>
                        Per {u}
                      </option>
                    ))}
                  </select>
                ) : (
                  <select value={form.condition} onChange={(e) => setField('condition', e.target.value)}>
                    {ITEM_CONDITIONS.map((c) => (
                      <option key={c} value={c}>
                        {c.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                )}
              </label>
            </div>

            {!need && isRent && (
              <label className="form-field">
                Item Condition *
                <select value={form.condition} onChange={(e) => setField('condition', e.target.value)}>
                  {ITEM_CONDITIONS.map((c) => (
                    <option key={c} value={c}>
                      {c.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="form-field">
              Location *
              <input
                required
                minLength="2"
                maxLength="100"
                value={form.location}
                onChange={(e) => setField('location', e.target.value)}
                placeholder="e.g. ECC 12, Food Court 2, Multiplex"
              />
            </label>

            <label className="form-field">
              Description *
              <textarea
                required
                minLength="2"
                maxLength="2000"
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
                placeholder="Provide accurate details about item condition, specifications, or pickup arrangements."
              />
            </label>

            {!need && (
              <label className="form-field">
                Photos (up to 5 images, max 5MB each)
                <input
                  type="file"
                  multiple
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => setField('images', Array.from(e.target.files || []))}
                />
              </label>
            )}

            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}

            <button
              className="primary submit"
              disabled={submitting}
              aria-busy={submitting}
            >
              {submitting ? '⌁ Submitting…' : `⌁ ${need ? 'Post Need' : 'Post Listing'}`}
            </button>
          </form>

          <aside>
            <TipBox listing={!need} />
          </aside>
        </div>
      </main>
    </>
  );
}
