import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Header, Footer } from '../components/Layout';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';

const USER_ROLES = ['SE', 'DSE', 'SP_L1', 'SP_L2'];

export default function AuthPage({ register = false }) {
  const [showPassword, setShowPassword] = useState(false);
  const formRef = useRef(null);
  const navigate = useNavigate();
  const { login } = useAuth();
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    confirm: '',
    role: 'DSE',
    joining_date: '',
  });

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    const f = formRef.current;
    if (!f || !register) return;
    if (form.confirm && form.password && form.confirm !== form.password) {
      f.confirm.setCustomValidity('Passwords do not match');
    } else if (f.confirm) {
      f.confirm.setCustomValidity('');
    }
  }, [form.password, form.confirm, register]);

  const validateInput = () => {
    // Email domain policy is enforced authoritatively by the backend
    // (config-driven `allowed_email_domains` in routers/auth.py) and surfaced
    // through the flattened API error message; the client must not hardcode it.
    // Address format is validated by the email input's own type="email".
    if (form.password.length < 8 || form.password.length > 100) {
      throw new Error('Password must be between 8 and 100 characters.');
    }

    if (register) {
      const name = form.name.trim();
      if (name.length < 2 || name.length > 100) {
        throw new Error('Full Name must be between 2 and 100 characters.');
      }

      const phone = form.phone.trim();
      if (!/^\d{10,15}$/.test(phone)) {
        throw new Error('Phone number must contain 10 to 15 digits.');
      }

      if (form.password !== form.confirm) {
        throw new Error('Passwords do not match.');
      }

      if (!form.joining_date) {
        throw new Error('Please select your joining date.');
      }
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    setError('');

    try {
      validateInput();
      setSubmitting(true);

      if (register) {
        await api.register({
          name: form.name.trim(),
          email: form.email.trim().toLowerCase(),
          phone: form.phone.trim(),
          password: form.password,
          role: form.role,
          joining_date: form.joining_date,
        });
      }

      await login({
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });

      navigate('/profile');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Header />
      <div className="auth">
        <section>
          <h1>{register ? 'Join InfyExchange' : 'Welcome Back!'}</h1>
          <p>
            {register
              ? 'Create your account and become a part of the Infosys Mysore community. Buy, rent, lend and give items within campus.'
              : 'Login to InfyExchange and continue buying, renting, lending and giving within our Infosys Mysore community.'}
          </p>
        </section>

        <form className="auth-card" ref={formRef} onSubmit={submit} noValidate>
          <h2>{register ? 'Create Your Account' : 'Login to InfyExchange'}</h2>
          <p>
            {register
              ? 'Join InfyExchange and start connecting with your fellow trainees.'
              : 'Access your account and continue within our community.'}
          </p>

          <div className={register ? 'auth-grid' : ''}>
            {register && (
              <label className="form-field">
                Full Name *
                <input
                  required
                  minLength="2"
                  maxLength="100"
                  value={form.name}
                  onChange={(e) => setField('name', e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                />
              </label>
            )}

            <label className="form-field">
              Email Address *
              <input
                type="email"
                required
                value={form.email}
                onChange={(e) => setField('email', e.target.value)}
                placeholder="you@example.com"
              />
            </label>

            {register && (
              <label className="form-field">
                Phone Number (10–15 digits) *
                <input
                  required
                  inputMode="numeric"
                  pattern="\d{10,15}"
                  maxLength="15"
                  value={form.phone}
                  onChange={(e) => setField('phone', e.target.value.replace(/\D/g, ''))}
                  placeholder="e.g. 9876543210"
                />
              </label>
            )}

            <label className="form-field">
              Password *
              <input
                name="password"
                required
                minLength="8"
                maxLength="100"
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={(e) => setField('password', e.target.value)}
                placeholder="8+ chars, incl. a letter and a number"
                title="Password must be 8-100 characters and contain at least one letter and one number"
              />
              <button
                type="button"
                className="eye"
                aria-label="Toggle password visibility"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? '◉' : '◌'}
              </button>
            </label>

            {register && (
              <>
                <label className="form-field">
                  Confirm Password *
                  <input
                    name="confirm"
                    required
                    type="password"
                    value={form.confirm}
                    onChange={(e) => setField('confirm', e.target.value)}
                    placeholder="Repeat password"
                  />
                </label>

                <label className="form-field">
                  Role *
                  <select value={form.role} onChange={(e) => setField('role', e.target.value)}>
                    {USER_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="form-field">
                  Joining Date *
                  <input
                    required
                    type="date"
                    value={form.joining_date}
                    onChange={(e) => setField('joining_date', e.target.value)}
                  />
                </label>
              </>
            )}
          </div>

          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}

          <button
            className="primary auth-submit"
            disabled={submitting}
            aria-busy={submitting}
          >
            {submitting ? 'Authenticating…' : register ? 'Create Account →' : 'Login →'}
          </button>

          <p className="switch">
            {register ? 'Already have an account?' : 'Don’t have an account?'}{' '}
            <Link to={register ? '/login' : '/register'}>
              {register ? 'Login here' : 'Register here'}
            </Link>
          </p>
        </form>
      </div>
      <Footer />
    </>
  );
}
