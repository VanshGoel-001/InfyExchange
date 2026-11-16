import { useRef, useState } from 'react';
import { toFailure } from '../services/api';
import { newKey } from '../utils/idempotency';
import { failureCopy } from '../utils/messages';
import { splitServerError } from '../utils/validate';

/**
 * Form state with validation that behaves the way people expect:
 *  - a field's problem appears after they leave it (blur) or after they press submit,
 *    never while they are still typing their first character;
 *  - problems the server reports are shown next to the right field and clear when that field is edited;
 *  - submit is locked while a request is running, and the first invalid field gets focus.
 *
 * `validate(values)` returns { fieldName: 'message' } for every problem.
 * Inputs need `name={field}` so focus can find them.
 */
export function useForm(initial, validate, fieldNames = Object.keys(initial), { context = 'save' } = {}) {
  const [values, setValues] = useState(initial);
  const [touched, setTouched] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [remote, setRemote] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  // Set when the request itself failed (not a problem with what was typed): { text, action } for one inline line.
  const [failure, setFailure] = useState(null);
  const lastSubmit = useRef(null);
  // Sent with a write so a retry after a lost answer cannot create it twice. It stays the same across retries of
  // the same form, and a new one starts after a success or as soon as anything in the form changes.
  const keyRef = useRef(null);

  const problems = validate(values);

  const set = (key, value) => {
    keyRef.current = null;
    setValues((current) => ({ ...current, [key]: value }));
    setRemote((current) => {
      if (!(key in current)) return current;
      const { [key]: _removed, ...rest } = current;
      return rest;
    });
    setFormError('');
  };

  const blur = (key) => setTouched((current) => ({ ...current, [key]: true }));

  const error = (key) => (((submitted || touched[key]) && problems[key]) || remote[key] || '');

  // Props shared by every input: wire value, change, blur and the accessible error state in one spread.
  const bind = (key) => ({
    name: key,
    value: values[key],
    onChange: (event) => set(key, event.target.value),
    onBlur: () => blur(key),
    'aria-invalid': error(key) ? 'true' : undefined,
  });

  const execute = async (onValid, form) => {
    if (busy) return;
    lastSubmit.current = onValid;
    setSubmitted(true);
    setFormError('');
    setFailure(null);

    const first = Object.keys(problems)[0];
    if (first) {
      form?.elements[first]?.focus();
      return;
    }

    setBusy(true);
    try {
      await onValid(values);
      keyRef.current = null;
    } catch (err) {
      if (err?.name === 'AbortError') return;
      const problem = toFailure(err);
      if (['invalid', 'conflict', 'limited'].includes(problem.kind)) {
        // Something about what was typed: show it next to the field, or as one line for the form.
        const { fields, general } = splitServerError(err, fieldNames);
        setRemote(fields);
        setFormError(general);
      } else {
        // The request itself failed. Everything typed stays; one line and a Retry.
        const { text, action } = failureCopy(problem, context);
        setFailure({ text, action });
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = (onValid) => async (event) => {
    event.preventDefault();
    await execute(onValid, event.currentTarget);
  };

  // Try the same submit again with what is on screen (the Retry next to the error).
  const resubmit = () => (lastSubmit.current ? execute(lastSubmit.current) : undefined);

  const idempotencyKey = () => {
    keyRef.current ??= newKey();
    return keyRef.current;
  };

  return { values, set, bind, error, handleSubmit, resubmit, idempotencyKey, busy, formError, failure, setFormError };
}
