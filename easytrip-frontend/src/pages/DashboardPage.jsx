import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listConversations, createConversation } from '../api/chat';
import { listBookings } from '../api/bookings';

export default function DashboardPage() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([listConversations(), listBookings()])
      .then(([conversationsData, bookingsData]) => {
        setConversations(conversationsData);
        setBookings(bookingsData);
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleNewChat() {
    const conversation = await createConversation();
    navigate(`/chat/${conversation.id}`);
  }

  if (loading) return <p>Caricamento...</p>;

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <h1>Dashboard</h1>
        <button type="button" onClick={handleNewChat}>
          + Nuova chat
        </button>
      </section>

      <section>
        <h2>Conversazioni recenti</h2>
        {conversations.length === 0 && <p>Nessuna conversazione ancora. Inizia una nuova chat!</p>}
        <ul>
          {conversations.slice(0, 5).map((c) => (
            <li key={c.id}>
              <Link to={`/chat/${c.id}`}>{c.title || `Conversazione #${c.id}`}</Link>
            </li>
          ))}
        </ul>
        {conversations.length > 0 && <Link to="/chat">Vai alla chat →</Link>}
      </section>

      <section>
        <h2>Prenotazioni recenti</h2>
        {bookings.length === 0 && <p>Nessuna prenotazione ancora.</p>}
        <ul>
          {bookings.slice(0, 5).map((b) => (
            <li key={b.id}>
              <Link to={`/bookings/${b.id}`}>
                #{b.id} - {b.country} ({b.status}) - €{b.total_cost}
              </Link>
            </li>
          ))}
        </ul>
        {bookings.length > 0 && <Link to="/bookings">Vedi tutte →</Link>}
      </section>
    </div>
  );
}
