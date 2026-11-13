import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Check, Eye, EyeOff, Plus } from 'lucide-react';

const BANNER_ART = { need: '💭 🏸 🏓', activity: '📋 🤝 💬', sports: '🏸 ⚽ 🏓' };

export function Banner({ title, subtitle, kind = 'sports', action, to }) {
  return (
    <section className={`banner ${kind}`}>
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="banner-art" aria-hidden="true">{BANNER_ART[kind] ?? BANNER_ART.sports}</div>
      {action && (
        <div className="banner-action">
          <b>{kind === 'need' ? "Can't find what you need?" : 'Give your sports gear a second home.'}</b>
          <Link className="primary" to={to}>
            <Plus /> {action}
          </Link>
        </div>
      )}
    </section>
  );
}

/** A small coloured badge. `tone` is one of: blue, pink, purple, green, status, pending. */
export function Pill({ tone = 'blue', children }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

/** Label + control + message in one place, so every form reads and reports errors the same way. */
export function Field({ label, error, hint, required, children }) {
  return (
    <label className={`form-field${error ? ' has-error' : ''}`}>
      <span className="field-label">
        {label}
        {required && <abbr title="required" aria-hidden="true"> *</abbr>}
      </span>
      {children}
      {error ? (
        <small className="field-error" role="alert">{error}</small>
      ) : (
        hint && <small className="field-hint">{hint}</small>
      )}
    </label>
  );
}

/** Password input with a show/hide toggle that sits inside the box and never overlaps the text. */
export function PasswordInput({ autoComplete, ...props }) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="input-wrap">
      <input {...props} type={visible ? 'text' : 'password'} autoComplete={autoComplete} />
      <button
        type="button"
        className="eye"
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? <EyeOff /> : <Eye />}
      </button>
    </span>
  );
}

export function FormError({ children }) {
  return children ? <p role="alert" className="error">{children}</p> : null;
}

/** One-time success message handed over by the previous page: navigate(path, { state: { notice } }). */
export function Flash() {
  const { state } = useLocation();
  return state?.notice ? <p role="status" className="flash">{state.notice}</p> : null;
}

const LISTING_TIPS = [
  'Add clear, real photos of the item',
  'Describe its condition honestly',
  'Set a fair price',
  'Say where and when it can be picked up',
  'Be respectful to fellow trainees',
];

const NEED_TIPS = [
  'Say exactly what you are looking for',
  'Mention whether you want to buy, rent or borrow it',
  'For rent or borrow, say how long you need it',
  'Add your budget if you have one',
  'Say where you can pick it up',
  'Add specifics such as brand or size',
];

export function TipBox({ listing = false }) {
  return (
    <div className="tipbox">
      <h3>{listing ? 'Tips for a good listing' : 'Tips for a good request'}</h3>
      {(listing ? LISTING_TIPS : NEED_TIPS).map((tip) => (
        <p key={tip}>
          <Check aria-hidden="true" /> {tip}
        </p>
      ))}
    </div>
  );
}
