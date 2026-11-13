import { Navigate, useNavigate } from 'react-router-dom';
import { Header } from '../components/Layout';
import { Banner, Field, FormError } from '../components/Ui';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';
import { api } from '../services/api';
import { ROLES } from '../utils/labels';
import { LIMITS, todayISO, validateProfileDetails } from '../utils/validate';

const FIELDS = ['phone', 'role', 'joining_date'];

// Shown once, right after someone's first "Continue with Google".
// Google gives us a name and an email; everything else the marketplace needs is asked for here.
export default function CompleteProfilePage() {
  const { user, token, setUser } = useAuth();
  const navigate = useNavigate();
  const form = useForm({ phone: '', role: '', joining_date: '' }, validateProfileDetails, FIELDS);
  const { bind, set, error } = form;

  if (user.profile_complete) return <Navigate to="/profile" replace />;

  const submit = form.handleSubmit(async (values) => {
    const updated = await api.completeProfile(
      { phone: values.phone.trim(), role: values.role, joining_date: values.joining_date },
      token
    );
    setUser(updated);
    navigate('/listings', { replace: true });
  });

  return (
    <>
      <Header />
      <main className="wide">
        <Banner
          title={`Welcome, ${user.name.split(' ')[0]}!`}
          subtitle="One last step before you can post items or reply to listings."
        />
        <form className="form-card narrow" onSubmit={submit} noValidate>
          <h2>A few details about you</h2>
          <p className="form-lead">
            You signed in as <b>{user.email}</b>. Other trainees only see your phone number after you accept their request.
          </p>

          <Field label="Phone number" required error={error('phone')} hint="10 to 15 digits, numbers only.">
            <input
              {...bind('phone')}
              onChange={(event) => set('phone', event.target.value.replace(/\D/g, ''))}
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              maxLength={LIMITS.phone[1]}
              placeholder="10-digit mobile number"
            />
          </Field>

          <Field label="Your role" required error={error('role')}>
            <select {...bind('role')}>
              <option value="" disabled>Choose your role</option>
              {ROLES.map((role) => (
                <option key={role.value} value={role.value}>{role.option}</option>
              ))}
            </select>
          </Field>

          <Field label="Date you joined Infosys" required error={error('joining_date')}>
            <input {...bind('joining_date')} type="date" max={todayISO()} />
          </Field>

          <FormError>{form.formError}</FormError>

          <button className="primary submit" disabled={form.busy} aria-busy={form.busy}>
            {form.busy ? 'Saving…' : 'Save and continue'}
          </button>
        </form>
      </main>
    </>
  );
}
