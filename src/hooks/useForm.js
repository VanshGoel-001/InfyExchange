import { useState } from 'react';
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
export function useForm(initial, validate, fieldNames = Object.keys(initial)) {
  const [values, setValues] = useState(initial);
  const [touched, setTouched] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [remote, setRemote] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  const problems = validate(values);

  const set = (key, value) => {
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

  const handleSubmit = (onValid) => async (event) => {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    setSubmitted(true);
    setFormError('');

    const first = Object.keys(problems)[0];
    if (first) {
      form.elements[first]?.focus();
      return;
    }

    setBusy(true);
    try {
      await onValid(values);
    } catch (err) {
      if (err?.name === 'AbortError') return;
      const { fields, general } = splitServerError(err, fieldNames);
      setRemote(fields);
      setFormError(general);
    } finally {
      setBusy(false);
    }
  };

  return { values, set, bind, error, handleSubmit, busy, formError, setFormError };
}
