import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const EMPTY_FORM = {
  username: '',
  email: '',
  password: '',
  password_confirm: '',
  first_name: '',
  last_name: '',
  phone_number: '',
};

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await register(form);
      navigate('/', { replace: true });
    } catch (err) {
      const data = err.response?.data;
      const message = data
        ? Object.values(data).flat().join(' ')
        : 'Registrazione non riuscita.';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>Crea un account</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Username
          <input name="username" value={form.username} onChange={handleChange} required />
        </label>
        <label>
          Email
          <input
            type="email"
            name="email"
            value={form.email}
            onChange={handleChange}
            required
          />
        </label>
        <label>
          Nome
          <input name="first_name" value={form.first_name} onChange={handleChange} />
        </label>
        <label>
          Cognome
          <input name="last_name" value={form.last_name} onChange={handleChange} />
        </label>
        <label>
          Telefono
          <input name="phone_number" value={form.phone_number} onChange={handleChange} />
        </label>
        <label>
          Password
          <input
            type="password"
            name="password"
            value={form.password}
            onChange={handleChange}
            required
          />
        </label>
        <label>
          Conferma password
          <input
            type="password"
            name="password_confirm"
            value={form.password_confirm}
            onChange={handleChange}
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creazione in corso...' : 'Registrati'}
        </button>
      </form>
      <p>
        Hai già un account? <Link to="/login">Accedi</Link>
      </p>
    </div>
  );
}
