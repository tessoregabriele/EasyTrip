function formatDate(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('it-IT', { day: 'numeric', month: 'long' });
}

export default function HotelStayCard({ hotelName, nights, checkIn, checkOut }) {
  const total = nights.reduce((sum, n) => sum + Number(n.price_per_night), 0);
  const anyPending = nights.some((n) => n.approvato === false);

  return (
    <div className="itinerary-item-card itinerary-item-card--hotel">
      <h4>
        {hotelName}
        {anyPending && <span className="badge badge--pending"> da rivedere</span>}
      </h4>
      <p>
        {formatDate(checkIn)} → {formatDate(checkOut)} ({nights.length} {nights.length === 1 ? 'notte' : 'notti'})
      </p>
      <ul>
        {nights.map((n) => (
          <li key={n.date}>
            {formatDate(n.date)}: €{n.price_per_night}/notte
          </li>
        ))}
      </ul>
      <p className="itinerary-item-card__footer">Totale soggiorno: €{total.toFixed(2)}</p>
    </div>
  );
}
