import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Header, Footer } from '../components/Layout';
import { Field, FormError, PasswordInput } from '../components/Ui';
import GoogleButton, { GOOGLE_CLIENT_ID } from '../components/GoogleButton';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';
import { api } from '../services/api';
import { ROLES } from '../utils/labels';
import { LIMITS, normalizePhone, todayISO, validateLogin, validateRegister } from '../utils/validate';

const REGISTER_FIELDS = ['name', 'email', 'phone', 'password', 'confirm', 'role', 'joining_date'];

export default function AuthPage({ register = false }) {
  const navigate = useNavigate();
  const { login, loginWithGoogle } = useAuth();
  const [googleBusy, setGoogleBusy] = useState(false);

  const form = useForm(
    { name: '', email: '', phone: '', password: '', confirm: '', role: '', joining_date: '' },
    register ? validateRegister : validateLogin,
    // Login failures ("Invalid email or password") belong to the form, not to one field.
    register ? REGISTER_FIELDS : []
  );
  const { values, bind, error } = form;

  const submit = form.handleSubmit(async () => {
    const email = values.email.trim().toLowerCase();
    if (register) {
      await api.register({
        name: values.name.trim(),
        email,
        phone: normalizePhone(values.phone),
        password: values.password,
        role: values.role,
        joining_date: values.joining_date,
      });
    }
    await login({ email, password: values.password });
    // The welcome email often lands in spam, so say where to look.
    navigate('/listings', register ? { state: { toast: 'Welcome! We sent you a welcome email. If you do not see it in your inbox, please check your spam folder.' } } : undefined);
  });

  const continueWithGoogle = async (credential) => {
    setGoogleBusy(true);
    form.setFormError('');
    try {
      const profile = await loginWithGoogle(credential);
      navigate(profile.profile_complete ? '/listings' : '/complete-profile');
    } catch (err) {
      form.setFormError(err.message);
    } finally {
      setGoogleBusy(false);
    }
  };

  const busy = form.busy || googleBusy;

  return (
    <>
      <Header />
      <div className="auth">
        <section>
          <h1>{register ? 'Join InfyExchange' : 'Welcome back'}</h1>
          {!register && <p>Log in to see your items, requests and enquiries from other trainees.</p>}
        </section>

        <form className="auth-card" onSubmit={submit} noValidate>
          <h2>{register ? 'Create your account' : 'Log in'}</h2>

          {GOOGLE_CLIENT_ID && (
            <>
              <GoogleButton
                key={register ? 'signup' : 'login'}
                text={register ? 'signup_with' : 'signin_with'}
                onCredential={continueWithGoogle}
                onError={form.setFormError}
              />
              <div className="or-divider"><span>or use your email</span></div>
            </>
          )}

          <div className={register ? 'auth-grid' : ''}>
            {register && (
              <Field label="Full name" error={error('name')}>
                <input {...bind('name')} autoComplete="name" maxLength={LIMITS.name[1]} />
              </Field>
            )}

            <Field label="Email" error={error('email')}>
              <input {...bind('email')} type="email" autoComplete="email" />
            </Field>

            {register && (
              <Field label="Phone number" error={error('phone')}>
                <input {...bind('phone')} type="tel" inputMode="tel" autoComplete="tel" maxLength={LIMITS.phoneInput} />
              </Field>
            )}

            <Field label="Password" error={error('password')}>
              <PasswordInput
                {...bind('password')}
                autoComplete={register ? 'new-password' : 'current-password'}
                maxLength={LIMITS.password[1]}
              />
            </Field>

            {register && (
              <>
                <Field label="Confirm password" error={error('confirm')}>
                  <PasswordInput {...bind('confirm')} autoComplete="new-password" maxLength={LIMITS.password[1]} />
                </Field>

                <Field label="Your role" error={error('role')}>
                  <select {...bind('role')}>
                    <option value="" disabled />
                    {ROLES.map((role) => (
                      <option key={role.value} value={role.value}>{role.option}</option>
                    ))}
                  </select>
                </Field>

                <Field label="Date you joined Infosys" error={error('joining_date')}>
                  <input {...bind('joining_date')} type="date" max={todayISO()} />
                </Field>
              </>
            )}
          </div>

          <FormError>{form.formError}</FormError>

          <button className="primary auth-submit" disabled={busy} aria-busy={busy}>
            {form.busy ? (register ? 'Creating your account…' : 'Logging in…') : register ? 'Create account' : 'Log in'}
          </button>

          <p className="switch">
            {register ? 'Already have an account?' : 'New to InfyExchange?'}{' '}
            <Link to={register ? '/login' : '/register'}>{register ? 'Log in' : 'Create an account'}</Link>
          </p>
        </form>
      </div>
      <Footer />
    </>
  );
}
