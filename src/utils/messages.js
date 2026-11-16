// Every failure message a person can see lives here: one short line plus (at most) one action.
// No status codes, no "Failed to fetch", no log text. The technical detail goes to the console and the server log.

// [line, action label]
const COPY = {
  listings: ["Couldn't load listings.", 'Retry'],
  needs: ["Couldn't load needs.", 'Retry'],
  stat: ['Unavailable.', 'Retry'],
  post: ["Couldn't post. Details saved.", 'Retry'],
  save: ["Couldn't save. Details saved.", 'Retry'],
  enquiry: ["Couldn't send.", 'Try again'],
  notifications: ["Couldn't load.", 'Retry'],
  chat: ['Not sent.', 'Tap to retry'],
  search: ['Search unavailable.', 'Retry'],
  generic: ['Something went wrong.', 'Retry'],
};

export const SESSION_MESSAGE = 'Please log in again.';
export const OFFLINE_MESSAGE = "You're offline.";
export const NO_ACCESS_MESSAGE = 'No access.';

/**
 * Turn a failed result ({ kind, message, ref } from `safe()`) into what to show: { text, action, ref }.
 * `context` picks the wording for what was being attempted (see COPY). Problems the person can fix themselves
 * (a bad value, a duplicate, "slow down") keep the server's own plain wording and offer no retry.
 */
export function failureCopy(error, context = 'generic') {
  const ref = error?.ref ?? null;
  const kind = error?.kind;

  if (kind === 'auth') return { text: SESSION_MESSAGE, action: null, ref };
  if (kind === 'forbidden') return { text: NO_ACCESS_MESSAGE, action: null, ref };
  if (kind === 'offline' || (typeof navigator !== 'undefined' && navigator.onLine === false)) {
    return { text: OFFLINE_MESSAGE, action: null, ref };
  }
  if ((kind === 'invalid' || kind === 'conflict' || kind === 'limited') && error.message) {
    return { text: error.message, action: null, ref };
  }

  const [text, action] = COPY[context] ?? COPY.generic;
  return { text, action, ref };
}
