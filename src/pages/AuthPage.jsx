import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Header, Footer } from '../components/Layout';
import { Field, FormError, PasswordInput } from '../components/Ui';
import GoogleButton, { GOOGLE_CLIENT_ID } from '../components/GoogleButton';
import { useAuth } from '../context/AuthContext';
import { useForm } from '../hooks/useForm';
import { api } from '../services/api';
import { ROLES } from '../utils/labels';
import { LIMITS, todayISO, validateLogin, validateRegister } from '../utils/validate';

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
  const { values, bind, set, error } = form;

  const submit = form.handleSubmit(async () => {
    const email = values.email.trim().toLowerCase();
    if (register) {
      await api.register({
        name: values.name.trim(),
        email,
        phone: values.phone.trim(),
        password: values.password,
        role: values.role,
        joining_date: values.joining_date,
      });
    }
    await login({ email, password: values.password });
    navigate('/listings');
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
          <p>
            {register
              ? 'Buy, rent, borrow or give away sports gear with other Infosys Mysore trainees. It takes a minute to sign up.'
              : 'Log in to see your items, requests and enquiries from other trainees.'}
          </p>
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
              {register && <div className="google-note">With Google you will add your phone number on the next screen.</div>}
              <div className="or-divider"><span>or use your email</span></div>
            </>
          )}

          <div className={register ? 'auth-grid' : ''}>
            {register && (
              <Field label="Full name" required error={error('name')}>
                <input {...bind('name')} autoComplete="name" placeholder="e.g. Rahul Sharma" maxLength={LIMITS.name[1]} />
              </Field>
            )}

            <Field label="Email" required error={error('email')} hint={register ? 'Only approved email domains can sign up.' : undefined}>
              <input {...bind('email')} type="email" autoComplete="email" placeholder="yourname@gmail.com" />
            </Field>

            {register && (
              <Field label="Phone number" required error={error('phone')} hint="Shared only with people whose request you accept.">
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
            )}

            <Field
              label="Password"
              required
              error={error('password')}
              hint={register ? 'At least 8 characters, with a letter and a number.' : undefined}
            >
              <PasswordInput
                {...bind('password')}
                autoComplete={register ? 'new-password' : 'current-password'}
                maxLength={LIMITS.password[1]}
                placeholder={register ? 'Create a password' : 'Your password'}
              />
            </Field>

            {register && (
              <>
                <Field label="Confirm password" required error={error('confirm')}>
                  <PasswordInput {...bind('confirm')} autoComplete="new-password" maxLength={LIMITS.password[1]} placeholder="Type it again" />
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
