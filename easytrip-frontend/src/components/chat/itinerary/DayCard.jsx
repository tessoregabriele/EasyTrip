function formatDate(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('it-IT', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

export default function DayCard({ date, activities }) {
  return (
    <div className="itinerary-item-card itinerary-item-card--day">
      <h4>{formatDate(date)}</h4>
      {activities.length === 0 ? (
        <p className="itinerary-item-card__muted">Nessuna attività in programma.</p>
      ) : (
        <ul>
          {activities.map((a) => (
            <li key={a.activity_id}>
              {a.activity_name} - €{a.price}
              {a.approvato === false && <span className="badge badge--pending"> da rivedere</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
