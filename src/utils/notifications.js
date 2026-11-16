import { Clock } from 'lucide-react';
import { cleanName, initials } from './labels';

// Notifications arrive as structured fields (kind, actor_name, listing_title, detail, ...). The wording is built
// here, from templates, and rendered as plain text by React, so nothing a member typed can change the layout,
// become a link or be read as markup. There are no links inside a notification.

const MAX_FIRST_NAME = 18;
const MAX_LINE = 80;

const clip = (text, max) => {
  const clean = String(text ?? '').replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max - 1).trimEnd()}…` : clean;
};

// A web address in a preview becomes the word "link". (The server does this too; this is the safety net.)
const URL_IN_TEXT = /\b(?:https?:\/\/|ftp:\/\/|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|in|io|co|me|app|dev|xyz|link|ly|info)\b\S*/gi;
export const plainPreview = (text, max = MAX_LINE) => clip(String(text ?? '').replace(URL_IN_TEXT, 'link'), max);

// "Ravi Kumar Venkataramanan" -> "Ravi K."; a single name stays as it is. Empty when there is no usable name.
export function shortName(name) {
  const parts = cleanName(name).split(/\s+/).filter(Boolean);
  if (!parts.length) return '';
  const first = clip(parts[0], MAX_FIRST_NAME);
  return parts.length === 1 ? first : `${first} ${Array.from(parts[parts.length - 1])[0].toUpperCase()}.`;
}

// What follows the name in the title line.
const ACTIONS = {
  enquiry_received: 'sent an enquiry',
  new_message: 'sent a message',
  enquiry_accepted: 'accepted your enquiry',
  enquiry_declined: 'declined your enquiry',
  deal_closed: 'closed the deal with you',
  price_changed: 'changed the price',
  item_returned: 'marked it as returned',
  listing_removed: 'removed a listing',
};

const RECEIVED = {
  received: 'confirmed they got it',
  not_received: 'has not got it yet',
};

// System notices with nobody behind them. Every other kind needs a named sender or it is not shown.
const NO_SENDER = new Set(['enquiry_expired', 'enquiry_closed']);

const CHAT_KINDS = new Set(['new_message', 'enquiry_accepted', 'deal_closed', 'price_changed', 'item_returned', 'completion_reminder', 'received_answer']);
const ENQUIRY_KINDS = new Set(['enquiry_received', 'enquiry_declined', 'enquiry_closed', 'enquiry_expired']);

/**
 * Everything a row needs, or null when the notification must not be shown (it needs a sender and has none).
 * `title` is a list of { text, name } pieces (only the name is emphasised), `secondary` the muted line,
 * `avatar` the initials (null for system notices, which show a clock), and `to` where a tap goes.
 */
export function describeNotification(item) {
  const name = shortName(item.actor_name);
  const system = NO_SENDER.has(item.kind);
  if (!name && !system) return null;

  const listing = item.listing_title ? clip(item.listing_title, MAX_LINE) : '';

  let title;
  if (item.kind === 'completion_reminder') {
    title = [{ text: 'Your chat with ' }, { text: name, name: true }, { text: ' has gone quiet' }];
  } else if (item.kind === 'enquiry_expired') {
    title = [{ text: 'Your enquiry expired' }];
  } else if (item.kind === 'enquiry_closed') {
    title = [{ text: 'A listing is no longer available' }];
  } else {
    const action = item.kind === 'received_answer' ? RECEIVED[item.detail] ?? 'replied about the handover' : ACTIONS[item.kind] ?? 'has an update for you';
    title = [{ text: name, name: true }, { text: ` ${action}` }];
  }

  let secondary = listing;
  if (item.kind === 'new_message' && item.detail) secondary = plainPreview(item.detail);
  if (item.kind === 'price_changed' && item.detail) secondary = [clip(item.detail, 40), listing].filter(Boolean).join(' · ');

  // The related page: the chat, the enquiries page, or the listing itself.
  let to = '/listings';
  if (CHAT_KINDS.has(item.kind) && item.interest_id) to = `/chats/${item.interest_id}`;
  else if (ENQUIRY_KINDS.has(item.kind)) to = '/activity';
  else if (item.listing_id) to = `/listings/${item.listing_id}`;

  return { title, secondary, avatar: system ? null : initials(item.actor_name), Icon: Clock, to };
}

// "Just now", "5m ago", "2h ago", "Yesterday", "3d ago", then "14 Nov" (with the year when it is not this year).
// `date` is a Date; callers pass the parsed server time.
export function relativeTime(date, now = new Date()) {
  if (!date) return '';
  const seconds = Math.floor((now - date) / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (date >= midnight && hours < 24) return `${hours}h ago`;
  const yesterday = new Date(midnight.getTime() - 86_400_000);
  if (date >= yesterday) return 'Yesterday';
  const days = Math.floor((midnight - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86_400_000);
  if (days < 7) return `${days}d ago`;
  const options = date.getFullYear() === now.getFullYear() ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' };
  return date.toLocaleDateString('en-GB', options);
}
