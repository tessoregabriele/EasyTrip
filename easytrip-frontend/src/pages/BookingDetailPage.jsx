import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getBooking, confirmBooking, cancelBooking } from '../api/bookings';

const STATUS_LABELS = {
  draft: 'Bozza',
  confirmed: 'Confermata',
  cancelled: 'Annullata',
};

export default function BookingDetailPage() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);

  useEffect(() => {
    getBooking(bookingId)
      .then(setBooking)
      .finally(() => setLoading(false));
  }, [bookingId]);

  async function handleConfirm() {
    setActionPending(true);
    try {
      setBooking(await confirmBooking(bookingId));
    } finally {
      setActionPending(false);
    }
  }

  async function handleCancel() {
    setActionPending(true);
    try {
      setBooking(await cancelBooking(bookingId));
    } finally {
      setActionPending(false);
    }
  }

  if (loading) return <p>Caricamento...</p>;
  if (!booking) return <p>Prenotazione non trovata.</p>;

  return (
    <div className="booking-detail-page">
      <button type="button" onClick={() => navigate('/bookings')}>
        ← Torna alla lista
      </button>

      <h1>
        Prenotazione #{booking.id}{' '}
        <span className={`badge badge--${booking.status}`}>
          {STATUS_LABELS[booking.status] ?? booking.status}
        </span>
      </h1>
      <p>
        Destinazione: <strong>{booking.country}</strong> - Mese: {booking.travel_month} - Budget: €
        {booking.total_budget}
      </p>

      <section>
        <h2>Voli</h2>
        <ul>
          {booking.flights.map((f) => (
            <li key={f.id}>
              {f.direction === 'outbound' ? 'Andata' : 'Ritorno'}: {f.flight_number}{' '}
              {f.departure_airport} → {f.arrival_airport} (
              {new Date(f.departure_datetime).toLocaleString('it-IT')}) - €{f.price}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Hotel</h2>
        <ul>
          {booking.hotel_stays.map((s) => (
            <li key={s.id}>
              {s.date}: {s.hotel_name} - €{s.price_per_night}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Attività</h2>
        <ul>
          {booking.activities.map((a) => (
            <li key={a.id}>
              {a.date}: {a.activity_name} - €{a.price}
            </li>
          ))}
        </ul>
      </section>

      <p>
        <strong>Totale: €{booking.total_cost}</strong>
      </p>

      {booking.status === 'draft' && (
        <div className="booking-detail-page__actions">
          <button type="button" onClick={handleConfirm} disabled={actionPending}>
            Conferma prenotazione
          </button>
          <button type="button" onClick={handleCancel} disabled={actionPending}>
            Annulla
          </button>
        </div>
      )}
      {booking.status === 'confirmed' && (
        <div className="booking-detail-page__actions">
          <button type="button" onClick={handleCancel} disabled={actionPending}>
            Annulla prenotazione
          </button>
        </div>
      )}
    </div>
  );
}
