import { useEffect, useState } from 'react';
import { getMe, updateMe } from '../api/auth';

export default function ProfilePage() {
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getMe()
      .then((data) =>
        setForm({
          ...data,
          preferred_activities: (data.preferred_activities ?? []).join(', '),
        })
      )
      .finally(() => setLoading(false));
  }, []);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setSaved(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        email: form.email,
        first_name: form.first_name,
        last_name: form.last_name,
        phone_number: form.phone_number,
        default_budget: form.default_budget || null,
        preferred_activities: form.preferred_activities
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const updated = await updateMe(payload);
      setForm({ ...updated, preferred_activities: (updated.preferred_activities ?? []).join(', ') });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  if (loading || !form) return <p>Caricamento...</p>;

  return (
    <div className="profile-page">
      <h1>Il mio profilo</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Username
          <input value={form.username} disabled />
        </label>
        <label>
          Email
          <input type="email" name="email" value={form.email} onChange={handleChange} required />
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
          Budget predefinito (€)
          <input
            type="number"
            name="default_budget"
            value={form.default_budget ?? ''}
            onChange={handleChange}
          />
        </label>
        <label>
          Attività preferite (separate da virgola)
          <input
            name="preferred_activities"
            value={form.preferred_activities}
            onChange={handleChange}
            placeholder="cultura, relax, avventura"
          />
        </label>
        {saved && <p className="form-success">Profilo aggiornato.</p>}
        <button type="submit" disabled={saving}>
          {saving ? 'Salvataggio...' : 'Salva modifiche'}
        </button>
      </form>
    </div>
  );
}
