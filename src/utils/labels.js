// Single source of truth for what the backend's enum values look like to a person.
// The API speaks in codes (SELL, TABLE_TENNIS, SP_L1); screens must never show those.
// Add a value here when the backend gains one, and every dropdown, badge and table follows.

export const CATEGORIES = [
  { value: 'BADMINTON', label: 'Badminton', icon: '🏸' },
  { value: 'TABLE_TENNIS', label: 'Table tennis', icon: '🏓' },
  { value: 'POOL_SNOOKER', label: 'Pool / Snooker', icon: '🎱' },
  { value: 'SQUASH', label: 'Squash', icon: '🥎' },
  { value: 'TENNIS', label: 'Tennis', icon: '🎾' },
  { value: 'CRICKET', label: 'Cricket', icon: '🏏' },
  { value: 'FOOTBALL', label: 'Football', icon: '⚽' },
  { value: 'BASKETBALL', label: 'Basketball', icon: '🏀' },
  { value: 'OTHER', label: 'Other', icon: '📦' },
];

// label = how it reads on a badge or filter; verb = how it reads when you post.
export const LISTING_TYPES = [
  { value: 'SELL', label: 'For sale', verb: 'Sell it', tone: 'pink' },
  { value: 'RENT', label: 'For rent', verb: 'Rent it out', tone: 'blue' },
  { value: 'LEND', label: 'To lend', verb: 'Lend it for free', tone: 'purple' },
  { value: 'GIVEAWAY', label: 'Free', verb: 'Give it away', tone: 'green' },
];

export const NEED_TYPES = [
  { value: 'BUY', label: 'Wants to buy', verb: 'Buy it', tone: 'blue' },
  { value: 'RENT', label: 'Wants to rent', verb: 'Rent it', tone: 'purple' },
  { value: 'BORROW', label: 'Wants to borrow', verb: 'Borrow it', tone: 'green' },
];

export const CONDITIONS = [
  { value: 'NEW', label: 'Brand new' },
  { value: 'LIKE_NEW', label: 'Like new' },
  { value: 'GOOD', label: 'Good' },
  { value: 'FAIR', label: 'Fair' },
  { value: 'POOR', label: 'Well used' },
];

// `label` is the short form (badges, tables); `option` adds what the code stands for.
export const ROLES = [
  { value: 'SE', label: 'SE', option: 'SE (Systems Engineer)' },
  { value: 'DSE', label: 'DSE', option: 'DSE (Digital Specialist Engineer)' },
  { value: 'SP_L1', label: 'SP L1', option: 'SP L1 (Specialist Programmer)' },
  { value: 'SP_L2', label: 'SP L2', option: 'SP L2 (Specialist Programmer)' },
];

export const LISTING_STATUSES = [
  { value: 'ACTIVE', label: 'Available', tone: 'status' },
  { value: 'SOLD', label: 'Sold', tone: 'pink' },
  { value: 'RENTED', label: 'Rented out', tone: 'purple' },
  { value: 'UNAVAILABLE', label: 'Unavailable', tone: 'pending' },
];

export const NEED_STATUSES = [
  { value: 'ACTIVE', label: 'Open', tone: 'status' },
  { value: 'FULFILLED', label: 'Fulfilled', tone: 'blue' },
  { value: 'CLOSED', label: 'Closed', tone: 'pending' },
];

export const INTEREST_STATUSES = [
  { value: 'PENDING', label: 'Waiting for reply', tone: 'pending' },
  { value: 'ACCEPTED', label: 'Accepted', tone: 'status' },
  { value: 'REJECTED', label: 'Declined', tone: 'pink' },
];

export const RENT_UNITS = [
  { value: 'hour', label: 'Per hour' },
  { value: 'day', label: 'Per day' },
  { value: 'week', label: 'Per week' },
  { value: 'month', label: 'Per month' },
];

// Fallback for a code we have not mapped yet: "TABLE_TENNIS" -> "Table tennis".
const humanise = (value) => {
  const text = String(value ?? '').replaceAll('_', ' ').toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
};

export const find = (list, value) => list.find((item) => item.value === value);
export const labelOf = (list, value) => (value == null || value === '' ? '' : find(list, value)?.label ?? humanise(value));
export const toneOf = (list, value) => find(list, value)?.tone ?? 'blue';
export const iconOf = (value) => find(CATEGORIES, value)?.icon ?? '📦';

export const formatPrice = (price, unit) => {
  const amount = Number(price);
  if (!(amount > 0)) return 'Free';
  return `₹${amount.toLocaleString('en-IN')}${unit ? ` / ${unit}` : ''}`;
};

// The API sends UTC timestamps without a zone suffix; without one the browser would read them as local time.
const toDate = (iso) => {
  if (!iso) return null;
  const text = String(iso);
  // A calendar date such as a joining date has no time or zone: keep it exactly as written.
  const calendar = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (calendar) return new Date(Number(calendar[1]), Number(calendar[2]) - 1, Number(calendar[3]));
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
};

export const formatDate = (iso) =>
  toDate(iso)?.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) ?? '';

export const formatDateTime = (iso) =>
  toDate(iso)?.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) ?? '';

export const daysLeft = (iso) => {
  const date = toDate(iso);
  if (!date) return '';
  const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return 'Expired';
  return days === 1 ? '1 day left' : `${days} days left`;
};

export const initials = (name) => (name || '?').trim().slice(0, 2).toUpperCase();
