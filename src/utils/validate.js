// Client-side checks. They mirror the backend's limits exactly (backend/app/schemas, routers/listings.py)
// so people hear about a mistake next to the field instead of from a failed request.
// The server stays authoritative: change a limit here and there together.

export const LIMITS = {
  name: [2, 100],
  // People may type spaces, hyphens or a +91 prefix; normalizePhone() reduces that to the bare number.
  phoneInput: 25,
  password: [8, 100],
  title: [2, 150],
  location: [2, 100],
  description: [2, 2000],
  duration: [0, 100],
  message: [0, 500],
  chatMessage: 1000,
  report: [5, 500],
  images: 5,
  imageBytes: 5 * 1024 * 1024,
  // The database stores whole rupees in a 32-bit column; this keeps typos from turning into a server error.
  maxAmount: 10_000_000,
};

export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const length = (value, label, [min, max]) => {
  const size = String(value ?? '').trim().length;
  if (size === 0 && min > 0) return `Enter ${label}.`;
  if (size < min) return `${label[0].toUpperCase()}${label.slice(1)} needs at least ${min} characters.`;
  if (size > max) return `${label[0].toUpperCase()}${label.slice(1)} can be at most ${max} characters (now ${size}).`;
  return '';
};

// Whole rupees only: the API rejects decimals.
const amount = (value, label, { required }) => {
  const text = String(value ?? '').trim();
  if (!text) return required ? `Enter ${label}.` : '';
  if (!/^\d+$/.test(text)) return `${label[0].toUpperCase()}${label.slice(1)} must be a whole number of rupees, like 500.`;
  const number = Number(text);
  if (required && number <= 0) return `${label[0].toUpperCase()}${label.slice(1)} must be more than ₹0.`;
  if (number > LIMITS.maxAmount) return `${label[0].toUpperCase()}${label.slice(1)} can be at most ₹${LIMITS.maxAmount.toLocaleString('en-IN')}.`;
  return '';
};

export const todayISO = () => {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
};

const email = (value) => {
  const text = String(value ?? '').trim();
  if (!text) return 'Enter your email address.';
  return EMAIL.test(text) ? '' : 'Enter a valid email address, like name@gmail.com.';
};

const password = (value) => {
  if (!value) return 'Create a password.';
  const [min, max] = LIMITS.password;
  if (value.length < min) return `Use at least ${min} characters.`;
  if (value.length > max) return `Use at most ${max} characters.`;
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) return 'Include at least one letter and one number.';
  return '';
};

// Same rule as the server (backend/app/utils/phone.py): strip spaces, hyphens and a leading +91.
export const normalizePhone = (value) => {
  const text = String(value ?? '').replace(/[\s-]/g, '');
  return text.startsWith('+91') ? text.slice(3) : text;
};

const phone = (value) => {
  if (!String(value ?? '').trim()) return 'Enter your phone number.';
  return /^[6-9][0-9]{9}$/.test(normalizePhone(value)) ? '' : 'Enter a valid 10-digit mobile number.';
};

const joiningDate = (value) => {
  if (!value) return 'Pick the date you joined Infosys.';
  return value > todayISO() ? 'The joining date cannot be in the future.' : '';
};

const compact = (errors) => Object.fromEntries(Object.entries(errors).filter(([, message]) => message));

export const validateLogin = (v) =>
  compact({
    email: email(v.email),
    password: v.password ? '' : 'Enter your password.',
  });

export const validateRegister = (v) =>
  compact({
    name: length(v.name, 'your name', LIMITS.name),
    email: email(v.email),
    phone: phone(v.phone),
    password: password(v.password),
    confirm: !v.confirm ? 'Type the password again.' : v.confirm !== v.password ? 'The two passwords do not match.' : '',
    role: v.role ? '' : 'Choose your role.',
    joining_date: joiningDate(v.joining_date),
  });

export const validateProfileDetails = (v) =>
  compact({
    phone: phone(v.phone),
    role: v.role ? '' : 'Choose your role.',
    joining_date: joiningDate(v.joining_date),
  });

export const validateProfileEdit = (v) =>
  compact({
    role: v.role ? '' : 'Choose your role.',
    joining_date: joiningDate(v.joining_date),
  });

const imageErrors = (files) => {
  if (files.length > LIMITS.images) return `You can add up to ${LIMITS.images} photos.`;
  for (const file of files) {
    if (!IMAGE_TYPES.includes(file.type)) return `"${file.name}" is not a JPEG, PNG or WebP picture.`;
    if (file.size > LIMITS.imageBytes) return `"${file.name}" is larger than 5 MB.`;
  }
  return '';
};

export const validateListing = (v) =>
  compact({
    title: length(v.title, 'a name for the item', LIMITS.title),
    price: v.listing_type === 'SELL' || v.listing_type === 'RENT' ? amount(v.price, 'the price', { required: true }) : '',
    location: length(v.location, 'a pickup location', LIMITS.location),
    description: length(v.description, 'a description', LIMITS.description),
    images: imageErrors(v.images),
  });

export const validateNeed = (v) =>
  compact({
    title: length(v.title, 'what you need', LIMITS.title),
    budget: amount(v.budget, 'the budget', { required: false }),
    duration: length(v.duration, 'the duration', LIMITS.duration),
    location: length(v.location, 'a location', LIMITS.location),
    description: length(v.description, 'a description', LIMITS.description),
  });

export const validateInterest = (v) => compact({ message: length(v.message, 'the message', LIMITS.message) });

export const validatePriceEdit = (v) => compact({ price: amount(v.price, 'the price', { required: true }) });

export const validateReport = (v) => compact({ reason: length(v.reason, 'what went wrong', LIMITS.report) });

// Turn a failed request into per-field messages plus one general message.
// The backend reports validation problems as "field: message" strings (see api.js).
export function splitServerError(error, knownFields) {
  const fields = {};
  const general = [];

  for (const [field, message] of Object.entries(error?.fields ?? {})) {
    if (knownFields.includes(field)) fields[field] = message;
    else general.push(message);
  }

  if (!Object.keys(fields).length && !general.length) {
    const message = error?.message || 'Something went wrong. Please try again.';
    // Plain messages such as "Phone number already registered" belong next to their field.
    const guess = knownFields.find((field) => new RegExp(`\\b${field.replace('_', '.?')}\\b`, 'i').test(message));
    const special = /gmail|domain/i.test(message) && knownFields.includes('email') ? 'email' : guess;
    if (special) fields[special] = message;
    else general.push(message);
  }

  return { fields, general: general.join(' ') };
}
