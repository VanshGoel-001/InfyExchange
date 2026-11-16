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
  { value: 'RENTED', label: 'Lent out', tone: 'purple' },
  { value: 'UNAVAILABLE', label: 'Unavailable', tone: 'pending' },
];

export const NEED_STATUSES = [
  { value: 'ACTIVE', label: 'Open', tone: 'status' },
  { value: 'FULFILLED', label: 'Fulfilled', tone: 'blue' },
  { value: 'CLOSED', label: 'Closed', tone: 'pending' },
];

// The API stores ACCEPTED and REJECTED; people read them as Chatting and Declined.
export const INTEREST_STATUSES = [
  { value: 'PENDING', label: 'Pending', tone: 'pending' },
  { value: 'ACCEPTED', label: 'Chatting', tone: 'status' },
  { value: 'REJECTED', label: 'Declined', tone: 'pink' },
  { value: 'CLOSED', label: 'Closed', tone: 'blue' },
];

// How the owner words "I closed the deal with this person", by what the item was on offer as.
export const CLOSE_DEAL_VERBS = { SELL: 'Sold to', RENT: 'Rented to', LEND: 'Lent to', GIVEAWAY: 'Given to' };

// One-tap replies the owner can attach when declining.
export const DECLINE_REPLIES = [
  'Already given to someone else',
  'No longer available',
  'Price is not negotiable',
  'Sorry, not a good fit',
];

// Why a listing or need is gone. An owner picks one of the first four (`choice` is how it reads in the picker);
// the last two are set by the system. `label` is how it reads in the admin Removed tab.
export const REMOVAL_REASONS = [
  { value: 'OWNER_SOLD', label: 'Sold or rented out', choice: 'Sold or rented out', tone: 'green' },
  { value: 'OWNER_UNAVAILABLE', label: 'No longer available', choice: 'No longer available', tone: 'blue' },
  { value: 'OWNER_MISTAKE', label: 'Posted by mistake', choice: 'Posted by mistake', tone: 'blue' },
  { value: 'OWNER_DELETED', label: 'Deleted by owner', choice: 'Another reason', tone: 'blue' },
  { value: 'ADMIN_REMOVED', label: 'Removed by an admin', tone: 'pink' },
  { value: 'EXPIRED', label: 'Expired', tone: 'pending' },
];
export const OWNER_REMOVAL_REASONS = REMOVAL_REASONS.slice(0, 4);

// A chat exists while the owner is chatting with someone, and with the one person the deal closed with.
export const hasChat = (enquiry) => enquiry.status === 'ACCEPTED' || (enquiry.status === 'CLOSED' && !!enquiry.deal_closed_at);

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

// The one way a rupee amount is written anywhere in the SPA: ₹ and Indian digit grouping (12,34,567).
// The server does the same for notification text (backend/app/utils/money.py); keep them in step.
export const formatRupees = (amount) => `₹${Number(amount).toLocaleString('en-IN')}`;

export const formatPrice = (price, unit) => {
  const amount = Number(price);
  if (!(amount > 0)) return 'Free';
  return `${formatRupees(amount)}${unit ? ` / ${unit}` : ''}`;
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

// The server's timestamps parsed as UTC, for callers that need a Date (relative times).
export const parseTime = toDate;

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

// Words that read as a web address ("http", "www", "x.com"); names may not contain them.
export const looksLikeLink = (text) => /\b(?:https?|ftp)\b|\bwww\b|\p{L}\.\p{L}{2,}/iu.test(text);

// A name made safe to show: link-like words and anything but letters, spaces and . ' - are dropped.
export const cleanName = (name) =>
  String(name ?? '')
    .split(/\s+/)
    .filter((word) => word && !looksLikeLink(word))
    .join(' ')
    .replace(/[^\p{L}\p{M} .'’-]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();

// First letter of the first and last name ("Asha Rao" -> "AR"); a single name gives its first two letters.
// Built from the cleaned name, so markup or links in an old name never reach an avatar.
export const initials = (name) => {
  const parts = cleanName(name).split(/\s+/).filter(Boolean).map((part) => Array.from(part));
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).join('').toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};
