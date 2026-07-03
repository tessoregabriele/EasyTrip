import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listBookings } from '../api/bookings';

const STATUS_LABELS = {
  draft: 'Bozza',
  confirmed: 'Confermata',
  cancelled: 'Annullata',
};

export default function BookingsListPage() {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listBookings()
      .then(setBookings)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Caricamento...</p>;

  return (
    <div className="bookings-list-page">
      <h1>Le mie prenotazioni</h1>
      {bookings.length === 0 && <p>Nessuna prenotazione ancora. Parla con l'assistente in chat per crearne una!</p>}
      <ul>
        {bookings.map((b) => (
          <li key={b.id}>
            <Link to={`/bookings/${b.id}`}>
              #{b.id} - {b.country} - {b.travel_month}/{new Date().getFullYear()} - €{b.total_cost}
              <span className={`badge badge--${b.status}`}> {STATUS_LABELS[b.status] ?? b.status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
