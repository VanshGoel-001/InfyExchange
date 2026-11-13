import { useEffect, useId, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';
import { Header } from '../components/Layout';
import { Banner, Field, FormError, TipBox } from '../components/Ui';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';
import { api } from '../services/api';
import { CATEGORIES, CONDITIONS, LISTING_TYPES, NEED_TYPES, RENT_UNITS } from '../utils/labels';
import { IMAGE_TYPES, LIMITS, validateListing, validateNeed } from '../utils/validate';

const LISTING_FIELDS = ['title', 'category', 'listing_type', 'price', 'price_unit', 'condition', 'location', 'description', 'images'];
const NEED_FIELDS = ['title', 'category', 'need_type', 'budget', 'duration', 'location', 'description'];

const size = (bytes) => (bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

// Radio group drawn as buttons: the choice is always visible and one tap changes it.
function ChoiceGroup({ legend, name, options, value, onChange }) {
  const labelId = useId();
  return (
    <div className="options" role="radiogroup" aria-labelledby={labelId}>
      <span className="field-label" id={labelId}>{legend}</span>
      <div className="option-row">
        {options.map((option) => (
          <label key={option.value} className={`option${value === option.value ? ' selected' : ''}`}>
            <input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} />
            {option.verb}
          </label>
        ))}
      </div>
    </div>
  );
}

export default function PostingPage({ need = false }) {
  const navigate = useNavigate();
  const { token } = useAuth();
  const abortRef = useRef(null);

  const form = useForm(
    {
      title: '',
      category: '',
      listing_type: 'SELL',
      need_type: 'BUY',
      price: '',
      price_unit: 'day',
      condition: '',
      duration: '',
      budget: '',
      location: '',
      description: '',
      images: [],
    },
    // Extra rules that depend on the whole form, on top of the shared length/number checks.
    (v) => ({
      ...(need ? validateNeed(v) : validateListing(v)),
      ...(v.category ? {} : { category: 'Choose a category.' }),
      ...(!need && !v.condition ? { condition: 'Choose the item’s condition.' } : {}),
    }),
    need ? NEED_FIELDS : LISTING_FIELDS
  );
  const { values, bind, set, error } = form;

  const isPaid = ['SELL', 'RENT'].includes(values.listing_type);
  const isRent = values.listing_type === 'RENT';
  const needsDuration = need && values.need_type !== 'BUY';

  useEffect(() => () => abortRef.current?.abort(), []);

  // Warn before leaving only while a post is actually being sent.
  useEffect(() => {
    if (!form.busy) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [form.busy]);

  const addPhotos = (event) => {
    const picked = Array.from(event.target.files || []);
    event.target.value = ''; // lets the same file be picked again after removing it
    if (picked.length) set('images', [...values.images, ...picked]);
  };

  const submit = form.handleSubmit(async (v) => {
    abortRef.current = new AbortController();
    const { signal } = abortRef.current;

    if (need) {
      await api.createNeed(
        {
          title: v.title.trim(),
          category: v.category,
          need_type: v.need_type,
          duration: needsDuration ? v.duration.trim() || null : null,
          budget: Number(v.budget || 0),
          location: v.location.trim(),
          description: v.description.trim(),
        },
        token,
        signal
      );
      navigate('/my-needs', { state: { notice: 'Your request is posted. Other trainees can now see it.' } });
      return;
    }

    const data = new FormData();
    data.append('title', v.title.trim());
    data.append('category', v.category);
    data.append('listing_type', v.listing_type);
    data.append('price', String(isPaid ? Number(v.price) : 0));
    if (isRent) data.append('price_unit', v.price_unit);
    data.append('condition', v.condition);
    data.append('location', v.location.trim());
    data.append('description', v.description.trim());
    v.images.forEach((file) => data.append('images', file));

    const created = await api.createListing(data, token, signal);
    navigate(`/listings/${created.id}`, { state: { notice: 'Your item is live. Other trainees can now find it.' } });
  });

  const types = need ? NEED_TYPES : LISTING_TYPES;
  const typeKey = need ? 'need_type' : 'listing_type';

  return (
    <>
      <Header />
      <main className="wide">
        <Banner
          title={need ? 'Post a request' : 'Post an item'}
          subtitle={
            need
              ? 'Tell the community what you are looking for. Someone might have it.'
              : 'Sell, rent, lend or give away something to fellow Infosys Mysore trainees.'
          }
          kind={need ? 'need' : 'sports'}
        />
        <div className="post-layout">
          <form className="form-card" onSubmit={submit} noValidate>
            <h2>{need ? 'What do you need?' : 'About your item'}</h2>

            <Field label={need ? 'What are you looking for?' : 'Item name'} required error={error('title')}>
              <input
                {...bind('title')}
                maxLength={LIMITS.title[1]}
                placeholder={need ? 'e.g. Badminton racket for a week' : 'e.g. Yonex Badminton Racket'}
              />
            </Field>

            <Field label="Category" required error={error('category')}>
              <select {...bind('category')}>
                <option value="" disabled>Choose a category</option>
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </Field>

            <ChoiceGroup
              legend={need ? 'How would you like to get it?' : 'What do you want to do with it?'}
              name={typeKey}
              options={types}
              value={values[typeKey]}
              onChange={(value) => set(typeKey, value)}
            />

            {!need && isPaid && (
              <div className="two">
                <Field label="Price (₹)" required error={error('price')} hint="Whole rupees, for example 500.">
                  <input {...bind('price')} type="text" inputMode="numeric" placeholder="e.g. 500" />
                </Field>
                {isRent && (
                  <Field label="Charged" required error={error('price_unit')}>
                    <select {...bind('price_unit')}>
                      {RENT_UNITS.map((u) => (
                        <option key={u.value} value={u.value}>{u.label}</option>
                      ))}
                    </select>
                  </Field>
                )}
              </div>
            )}
            {!need && !isPaid && <p className="form-lead">No price needed: this one is free.</p>}

            {!need && (
              <Field label="Condition" required error={error('condition')}>
                <select {...bind('condition')}>
                  <option value="" disabled>Choose the condition</option>
                  {CONDITIONS.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </Field>
            )}

            {need && (
              <div className="two">
                <Field label="Budget (₹), optional" error={error('budget')} hint="The most you can pay. Leave empty if open.">
                  <input {...bind('budget')} type="text" inputMode="numeric" placeholder="e.g. 300" />
                </Field>
                {needsDuration && (
                  <Field label="For how long?" error={error('duration')} hint="Optional.">
                    <input {...bind('duration')} maxLength={LIMITS.duration[1]} placeholder="e.g. 2 weeks" />
                  </Field>
                )}
              </div>
            )}

            <Field label={need ? 'Where can you pick it up?' : 'Pickup location'} required error={error('location')}>
              <input {...bind('location')} maxLength={LIMITS.location[1]} placeholder="e.g. ECC 12, Food Court 2, Multiplex" />
            </Field>

            <Field label="Description" required error={error('description')} hint={`${values.description.trim().length} / ${LIMITS.description[1]}`}>
              <textarea
                {...bind('description')}
                maxLength={LIMITS.description[1]}
                placeholder={
                  need
                    ? 'Describe what you need: brand, size, how you will use it.'
                    : 'Describe the item: brand, age, any scratches or missing parts.'
                }
              />
            </Field>

            {!need && (
              <Field
                label="Photos, optional"
                error={error('images')}
                hint={`Up to ${LIMITS.images} pictures (JPEG, PNG or WebP), 5 MB each.`}
              >
                <input type="file" name="images" multiple accept={IMAGE_TYPES.join(',')} onChange={addPhotos} />
              </Field>
            )}
            {!need && values.images.length > 0 && (
              <ul className="file-list">
                {values.images.map((file, index) => (
                  <li key={`${file.name}-${index}`}>
                    <span>{file.name} <small>{size(file.size)}</small></span>
                    <button
                      type="button"
                      aria-label={`Remove ${file.name}`}
                      onClick={() => set('images', values.images.filter((_, i) => i !== index))}
                    >
                      <X />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <FormError>{form.formError}</FormError>

            <button className="primary submit" disabled={form.busy} aria-busy={form.busy}>
              {form.busy ? 'Posting…' : need ? 'Post request' : 'Post item'}
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
