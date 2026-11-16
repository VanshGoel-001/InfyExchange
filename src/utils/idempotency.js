// A fresh random key for one write (a listing, a need, an enquiry, a message). The server remembers it for a day,
// so sending the same request again after a lost answer gives the first result instead of a second copy.
// getRandomValues works on plain http as well, unlike crypto.randomUUID.
export const newKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join('');
