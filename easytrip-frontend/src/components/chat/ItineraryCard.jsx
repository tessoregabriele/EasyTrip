import { buildItinerarySequence } from './itinerary/buildItinerarySequence';
import FlightCard from './itinerary/FlightCard';
import HotelStayCard from './itinerary/HotelStayCard';
import DayCard from './itinerary/DayCard';

export default function ItineraryCard({ itinerary, onConfirm, confirming }) {
  const { total_cost, total_budget } = itinerary;
  const items = buildItinerarySequence(itinerary);

  return (
    <div className="itinerary-timeline">
      <h3>Itinerario proposto</h3>

      <div className="itinerary-timeline__items">
        {items.map((item) => {
          switch (item.type) {
            case 'flight':
              return <FlightCard key={item.key} direction={item.direction} flight={item.flight} />;
            case 'hotel':
              return (
                <HotelStayCard
                  key={item.key}
                  hotelName={item.hotelName}
                  nights={item.nights}
                  checkIn={item.checkIn}
                  checkOut={item.checkOut}
                />
              );
            case 'day':
              return <DayCard key={item.key} date={item.date} activities={item.activities} />;
            default:
              return null;
          }
        })}
      </div>

      <div className="itinerary-card__footer">
        <strong>Totale: €{total_cost}</strong>
        {total_budget && <span> (budget: €{total_budget})</span>}
      </div>

      {onConfirm && (
        <div className="itinerary-card__actions">
          <button type="button" onClick={onConfirm} disabled={confirming}>
            {confirming ? 'Conferma in corso...' : 'Conferma questo itinerario'}
          </button>
        </div>
      )}
    </div>
  );
}
