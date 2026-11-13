import { Link } from 'react-router-dom';
import { Clock, MapPin, Sparkles, UserRound, Wallet } from 'lucide-react';
import { Pill } from './Ui';
import {
  CONDITIONS,
  LISTING_TYPES,
  NEED_TYPES,
  formatDate,
  formatPrice,
  iconOf,
  labelOf,
  toneOf,
} from '../utils/labels';

// p1..p7 are the placeholder gradients in style.css.
const shade = (i) => `p${(i % 7) + 1}`;

export function ProductCard({ item, i = 0 }) {
  return (
    <Link to={`/listings/${item.id}`} className="product">
      <div className={`product-img ${shade(i)}`}>
        {item.image_url ? <img src={item.image_url} alt={item.title} /> : <span aria-hidden="true">{iconOf(item.category)}</span>}
        <Pill tone={toneOf(LISTING_TYPES, item.listing_type)}>{labelOf(LISTING_TYPES, item.listing_type)}</Pill>
      </div>
      <div className="product-info">
        <b>{item.title}</b>
        <strong>{formatPrice(item.price, item.price_unit)}</strong>
        <small><Sparkles aria-hidden="true" /> {labelOf(CONDITIONS, item.condition)}</small>
        <small><MapPin aria-hidden="true" /> {item.location}</small>
      </div>
    </Link>
  );
}

export function NeedCard({ item, i = 0 }) {
  return (
    <article className="need-card">
      <div className={`need-image ${shade(i)}`}>
        <span aria-hidden="true">{iconOf(item.category)}</span>
        <Pill tone={toneOf(NEED_TYPES, item.need_type)}>{labelOf(NEED_TYPES, item.need_type)}</Pill>
      </div>
      <b>{item.title}</b>
      <p>{item.description}</p>
      <small><Clock aria-hidden="true" /> {item.duration ? `For ${item.duration}` : 'Duration is flexible'}</small>
      <small><Wallet aria-hidden="true" /> {item.budget > 0 ? `Budget ${formatPrice(item.budget)}` : 'No budget set'}</small>
      <small><MapPin aria-hidden="true" /> {item.location}</small>
      <small><UserRound aria-hidden="true" /> {item.user_name || 'A community member'} · {formatDate(item.created_at)}</small>
    </article>
  );
}
