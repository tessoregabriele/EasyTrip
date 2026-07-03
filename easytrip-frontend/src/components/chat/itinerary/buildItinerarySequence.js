function addDays(isoDate, amount) {
  // Calcolo tutto in UTC: se si parsa in ora locale e si formatta con
  // toISOString (che è sempre UTC), in fusi orari avanti rispetto a UTC
  // (es. Europe/Rome) il risultato "scivola" al giorno prima.
  const [year, month, day] = isoDate.split('-').map(Number);
  const d = new Date(Date.UTC(year, month - 1, day));
  d.setUTCDate(d.getUTCDate() + amount);
  return d.toISOString().slice(0, 10);
}

// Trasforma l'itinerario "piatto" (liste separate di notti hotel e attività
// giornaliere) in una sequenza ordinata di schede: volo andata, una scheda
// per ogni soggiorno (notti consecutive nello stesso hotel raggruppate
// insieme), una scheda per ogni giorno di quel soggiorno con le sue
// attività, e infine il volo di ritorno.
export function buildItinerarySequence(itinerary) {
  const { outbound_flight, return_flight, hotel_stays = [], daily_activities = [] } = itinerary;

  const sortedStays = [...hotel_stays].sort((a, b) => a.date.localeCompare(b.date));

  const stayGroups = [];
  for (const stay of sortedStays) {
    const lastGroup = stayGroups[stayGroups.length - 1];
    if (lastGroup && lastGroup.hotelId === stay.hotel_id) {
      lastGroup.nights.push(stay);
    } else {
      stayGroups.push({ hotelId: stay.hotel_id, hotelName: stay.hotel_name, nights: [stay] });
    }
  }

  const activitiesByDate = new Map();
  for (const activity of daily_activities) {
    if (!activitiesByDate.has(activity.date)) activitiesByDate.set(activity.date, []);
    activitiesByDate.get(activity.date).push(activity);
  }

  const items = [];

  if (outbound_flight) {
    items.push({ type: 'flight', key: 'flight-outbound', direction: 'outbound', flight: outbound_flight });
  }

  for (const group of stayGroups) {
    const lastNightDate = group.nights[group.nights.length - 1].date;
    items.push({
      type: 'hotel',
      key: `hotel-${group.hotelId}-${group.nights[0].date}`,
      hotelName: group.hotelName,
      nights: group.nights,
      checkIn: group.nights[0].date,
      checkOut: addDays(lastNightDate, 1),
    });
    for (const night of group.nights) {
      items.push({
        type: 'day',
        key: `day-${night.date}`,
        date: night.date,
        activities: activitiesByDate.get(night.date) ?? [],
      });
    }
  }

  if (return_flight) {
    items.push({ type: 'flight', key: 'flight-return', direction: 'return', flight: return_flight });
  }

  return items;
}
