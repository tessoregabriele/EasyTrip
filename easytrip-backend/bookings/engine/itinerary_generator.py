"""
Motore di generazione itinerario: dato budget, nazione, mese e preferenze
dell'utente, produce un itinerario completo (volo andata/ritorno, hotel per
ogni notte, un'attività per ogni giorno) che rispetta il budget e la
disponibilità reale nel catalogo.

Deliberatamente NON usa l'LLM per questa logica: il rispetto rigoroso dei
vincoli numerici (budget, disponibilità) è un problema di ricerca/selezione
sui dati, non di linguaggio. L'LLM invoca questo motore come tool e poi
presenta il risultato in linguaggio naturale (vedi chat/llm/tools.py).
"""
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Min

from catalog.models import Flight, HotelAvailability, ActivityAvailability
from catalog.rag.search import search_activities_semantic


DEFAULT_TRIP_NIGHTS = 4  # durata standard di un viaggio quando non altrimenti vincolata da un volo di ritorno specifico


@dataclass
class ItineraryResult:
    success: bool
    reason: str = ""
    outbound_flight: Flight | None = None
    return_flight: Flight | None = None
    hotel_stays: list[dict] = field(default_factory=list)   # [{hotel, date, price}]
    daily_activities: list[dict] = field(default_factory=list)  # [{activity, date, price}]
    total_cost: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        if not self.success:
            return {"success": False, "reason": self.reason}

        return {
            "success": True,
            "total_cost": str(self.total_cost),
            "outbound_flight": {
                "id": self.outbound_flight.id,
                "flight_number": self.outbound_flight.flight_number,
                "departure_airport": self.outbound_flight.departure_airport.iata_code,
                "arrival_airport": self.outbound_flight.arrival_airport.iata_code,
                "departure_datetime": self.outbound_flight.departure_datetime.isoformat(),
                "price": str(self.outbound_flight.price),
            },
            "return_flight": {
                "id": self.return_flight.id,
                "flight_number": self.return_flight.flight_number,
                "departure_airport": self.return_flight.departure_airport.iata_code,
                "arrival_airport": self.return_flight.arrival_airport.iata_code,
                "departure_datetime": self.return_flight.departure_datetime.isoformat(),
                "price": str(self.return_flight.price),
            },
            "hotel_stays": [
                {
                    "hotel_id": stay["hotel"].id,
                    "hotel_name": stay["hotel"].name,
                    "date": stay["date"].isoformat(),
                    "price_per_night": str(stay["price"]),
                }
                for stay in self.hotel_stays
            ],
            "daily_activities": [
                {
                    "activity_id": item["activity"].id,
                    "activity_name": item["activity"].name,
                    "date": item["date"].isoformat(),
                    "price": str(item["price"]),
                }
                for item in self.daily_activities
            ],
        }


def _month_date_range(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _find_round_trip_flights(country_id: int, year: int, month: int):
    """
    Trova la coppia di voli andata/ritorno più economica disponibile nel
    mese richiesto, verso una qualunque città della nazione di interesse.
    """
    month_start, month_end = _month_date_range(year, month)

    outbound_candidates = (
        Flight.objects.filter(
            arrival_airport__city__country_id=country_id,
            departure_datetime__date__gte=month_start,
            departure_datetime__date__lte=month_end,
            seats_available__gt=0,
        )
        .exclude(departure_airport__city__country_id=country_id)  # l'andata deve partire da fuori la nazione di destinazione
        .select_related('departure_airport', 'arrival_airport', 'arrival_airport__city')
        .order_by('price')
    )

    for outbound in outbound_candidates[:20]:  # limitiamo i candidati esaminati per restare efficienti
        # Cerchiamo un ritorno dalla stessa città visitata, in una data successiva all'andata
        return_candidates = (
            Flight.objects.filter(
                departure_airport=outbound.arrival_airport,
                arrival_airport=outbound.departure_airport,
                departure_datetime__date__gt=outbound.departure_datetime.date(),
                departure_datetime__date__lte=month_end + timedelta(days=5),  # piccolo margine oltre fine mese
                seats_available__gt=0,
            )
            .select_related('departure_airport', 'arrival_airport')
            .order_by('departure_datetime')
        )
        return_flight = return_candidates.first()
        if return_flight:
            return outbound, return_flight

    return None, None


def _select_hotel_for_stay(city_id: int, nights_dates: list[date], max_total_budget: Decimal):
    """
    Seleziona un singolo hotel disponibile per TUTTE le notti richieste nella
    città di destinazione, scegliendo tra quelli che rispettano il budget
    rimanente. Preferiamo un solo hotel per tutto il soggiorno (più realistico
    e più semplice da gestire per l'utente).
    """
    from catalog.models import Hotel

    candidate_hotels = Hotel.objects.filter(city_id=city_id).prefetch_related('availabilities')

    best_option = None
    for hotel in candidate_hotels:
        availabilities = {
            a.date: a for a in hotel.availabilities.filter(date__in=nights_dates, rooms_available__gt=0)
        }
        if len(availabilities) != len(nights_dates):
            continue  # questo hotel non ha disponibilità per tutte le notti richieste

        total_cost = sum(availabilities[d].price_per_night for d in nights_dates)
        if total_cost > max_total_budget:
            continue

        if best_option is None or total_cost < best_option['total_cost']:
            best_option = {
                'hotel': hotel,
                'total_cost': total_cost,
                'stays': [{'hotel': hotel, 'date': d, 'price': availabilities[d].price_per_night} for d in nights_dates],
            }

    return best_option


def _select_daily_activities(
    city_id: int, days: list[date], max_total_budget: Decimal, preferences: list[str],
):
    """
    Seleziona un'attività per ogni giorno del soggiorno, privilegiando quelle
    in linea con le preferenze dell'utente (categoria + similarità semantica
    RAG) e rispettando il budget rimanente complessivo per le attività.
    """
    from catalog.models import Activity

    selected = []
    remaining_budget = max_total_budget

    # Costruiamo una query testuale a partire dalle preferenze per il RAG
    preference_query = ", ".join(preferences) if preferences else "esperienza turistica generica"

    for day in days:
        available_qs = Activity.objects.filter(
            city_id=city_id,
            availabilities__date=day,
            availabilities__spots_available__gt=0,
        ).distinct()

        if preferences:
            # Prima proviamo a filtrare per categoria esatta (vincolo più forte)
            category_filtered = available_qs.filter(category__slug__in=preferences)
            candidates_qs = category_filtered if category_filtered.exists() else available_qs
        else:
            candidates_qs = available_qs

        if not candidates_qs.exists():
            continue  # nessuna attività disponibile questo giorno, saltiamo (l'itinerario resta valido senza)

        # Ranking semantico RAG sopra il filtro rigido già applicato
        ranked = search_activities_semantic(preference_query, queryset=candidates_qs, top_k=5)

        chosen = None
        for activity in ranked:
            availability = activity.availabilities.filter(date=day).first()
            if availability and availability.price <= remaining_budget:
                chosen = {'activity': activity, 'date': day, 'price': availability.price}
                break

        if chosen:
            selected.append(chosen)
            remaining_budget -= chosen['price']

    return selected, (max_total_budget - remaining_budget)


def generate_itinerary(
    country_id: int,
    total_budget: Decimal,
    travel_month: int,
    activity_preferences: list[str],
    travel_year: int | None = None,
) -> ItineraryResult:
    """
    Punto di ingresso principale del motore. Algoritmo (greedy, in ordine di
    priorità sui vincoli più rigidi):

    1. Trova la coppia di voli andata/ritorno più economica nel mese richiesto.
    2. Determina le notti di soggiorno dalle date dei voli.
    3. Seleziona un hotel che copra tutte le notti, nel budget rimanente.
    4. Seleziona un'attività per ogni giorno, secondo preferenze/RAG, nel
       budget rimanente.
    5. Se in un punto qualsiasi i vincoli non sono soddisfacibili, ritorna
       un risultato di fallimento con motivazione (l'LLM lo comunicherà
       all'utente e potrà proporre un nuovo tentativo con vincoli diversi).
    """
    year = travel_year or date.today().year
    # Se il mese richiesto è già passato quest'anno, assumiamo l'anno prossimo
    if travel_month < date.today().month or (travel_month == date.today().month and date.today().day > 25):
        year = date.today().year + (1 if travel_month <= date.today().month else 0)

    # --- 1. Voli ---
    outbound, return_flight = _find_round_trip_flights(country_id, year, travel_month)
    if not outbound or not return_flight:
        return ItineraryResult(
            success=False,
            reason="Nessun volo andata/ritorno disponibile per la nazione e il mese richiesti.",
        )

    flights_cost = outbound.price + return_flight.price
    if flights_cost > total_budget:
        return ItineraryResult(
            success=False,
            reason=f"Il costo dei voli ({flights_cost}€) supera già il budget totale ({total_budget}€).",
        )

    remaining_after_flights = total_budget - flights_cost

    # --- 2. Notti di soggiorno (dalle date dei voli) ---
    checkin = outbound.arrival_datetime.date()
    checkout = return_flight.departure_datetime.date()
    nights = [checkin + timedelta(days=i) for i in range((checkout - checkin).days)]
    if not nights:
        return ItineraryResult(success=False, reason="Date dei voli non compatibili con un soggiorno di almeno una notte.")

    destination_city_id = outbound.arrival_airport.city_id

    # --- 3. Hotel: alloca circa il 60% del budget residuo, il resto alle attività ---
    hotel_budget = remaining_after_flights * Decimal("0.6")
    hotel_option = _select_hotel_for_stay(destination_city_id, nights, hotel_budget)

    if not hotel_option:
        # Riproviamo con tutto il budget residuo, se il 60% non bastava
        hotel_option = _select_hotel_for_stay(destination_city_id, nights, remaining_after_flights)
        if not hotel_option:
            return ItineraryResult(
                success=False,
                reason="Nessun hotel disponibile per tutte le notti del soggiorno entro il budget residuo.",
            )

    remaining_after_hotel = remaining_after_flights - hotel_option['total_cost']

    # --- 4. Attività: un giorno per ogni notte (checkin incluso, checkout escluso) ---
    activities, activities_cost = _select_daily_activities(
        destination_city_id, nights, remaining_after_hotel, activity_preferences,
    )

    total_cost = flights_cost + hotel_option['total_cost'] + activities_cost

    return ItineraryResult(
        success=True,
        outbound_flight=outbound,
        return_flight=return_flight,
        hotel_stays=hotel_option['stays'],
        daily_activities=activities,
        total_cost=total_cost,
    )


def find_alternative_activity(
    city_id: int, day: date, max_budget: Decimal, preferences: list[str], exclude_activity_id: int | None = None,
) -> dict | None:
    """
    Trova UNA singola attività alternativa per un giorno specifico, usata dal
    flusso di revisione interattiva dell'itinerario (l'utente non è
    soddisfatto dell'attività proposta per un determinato giorno e ne vuole
    un'altra). Esclude esplicitamente l'attività attualmente assegnata, così
    non rischiamo di riproporre la stessa opzione che l'utente ha già scartato.

    Ritorna None se non viene trovata nessuna alternativa entro il budget.
    """
    from catalog.models import Activity

    available_qs = Activity.objects.filter(
        city_id=city_id,
        availabilities__date=day,
        availabilities__spots_available__gt=0,
    ).distinct()

    if exclude_activity_id:
        available_qs = available_qs.exclude(id=exclude_activity_id)

    if preferences:
        category_filtered = available_qs.filter(category__slug__in=preferences)
        candidates_qs = category_filtered if category_filtered.exists() else available_qs
    else:
        candidates_qs = available_qs

    if not candidates_qs.exists():
        return None

    preference_query = ", ".join(preferences) if preferences else "esperienza turistica generica"
    ranked = search_activities_semantic(preference_query, queryset=candidates_qs, top_k=5)

    for activity in ranked:
        availability = activity.availabilities.filter(date=day).first()
        if availability and availability.price <= max_budget:
            return {'activity': activity, 'date': day, 'price': availability.price}

    return None


def find_alternative_hotel(
    city_id: int, nights_dates: list[date], max_total_budget: Decimal, exclude_hotel_id: int | None = None,
):
    """
    Trova un hotel alternativo che copra TUTTE le notti richieste, usato dal
    flusso di revisione interattiva quando l'utente non è soddisfatto
    dell'hotel proposto. Esclude esplicitamente l'hotel corrente.

    Ritorna None se non viene trovata nessuna alternativa entro il budget.
    Riusa _select_hotel_for_stay, che già implementa la ricerca della
    combinazione più economica tra gli hotel disponibili.
    """
    from catalog.models import Hotel

    candidate_hotels = Hotel.objects.filter(city_id=city_id)
    if exclude_hotel_id:
        candidate_hotels = candidate_hotels.exclude(id=exclude_hotel_id)

    best_option = None
    for hotel in candidate_hotels.prefetch_related('availabilities'):
        availabilities = {
            a.date: a for a in hotel.availabilities.filter(date__in=nights_dates, rooms_available__gt=0)
        }
        if len(availabilities) != len(nights_dates):
            continue

        total_cost = sum(availabilities[d].price_per_night for d in nights_dates)
        if total_cost > max_total_budget:
            continue

        if best_option is None or total_cost < best_option['total_cost']:
            best_option = {
                'hotel': hotel,
                'total_cost': total_cost,
                'stays': [{'hotel': hotel, 'date': d, 'price': availabilities[d].price_per_night} for d in nights_dates],
            }

    return best_option
