const DIRECTION_LABELS = {
  outbound: 'Volo di andata',
  return: 'Volo di ritorno',
};

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('it-IT', { day: 'numeric', month: 'long' });
}

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

export default function FlightCard({ direction, flight }) {
  return (
    <div className="itinerary-item-card itinerary-item-card--flight">
      <h4>{DIRECTION_LABELS[direction] ?? 'Volo'}</h4>
      <p className="itinerary-item-card__route">
        {flight.departure_airport} → {flight.arrival_airport}
      </p>
      <p>
        {formatDate(flight.departure_datetime)}: decollo {formatTime(flight.departure_datetime)}
        {flight.arrival_datetime && <>, atterraggio {formatTime(flight.arrival_datetime)}</>}
      </p>
      <p className="itinerary-item-card__footer">
        Volo {flight.flight_number} - €{flight.price}
      </p>
    </div>
  );
}
