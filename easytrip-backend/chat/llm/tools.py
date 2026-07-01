"""
Tool esposti all'LLM per orchestrare la conversazione, la generazione
dell'itinerario e il flusso di revisione interattiva prima della conferma.

Principio guida (deciso insieme durante lo sviluppo): l'LLM NON genera mai
direttamente un itinerario, non fa calcoli di budget e non decide da solo
quando una prenotazione è "confermata" — si limita a raccogliere i
requisiti/feedback dalla conversazione e a invocare questi tool, che
eseguono codice Python deterministico (query sul catalogo, motore di
generazione, scrittura della Booking finale).

Flusso di revisione (deciso insieme): dopo genera_itinerario, l'utente vede
l'itinerario giorno per giorno e può chiedere di cambiare singoli pezzi
(un'attività di un giorno specifico, o l'hotel). Ogni sostituzione usa il
margine di budget residuo di TUTTO l'itinerario, non solo quello del
componente sostituito. Il ciclo si ripete finché l'utente non è
soddisfatto di ogni componente; solo allora un'ultima conferma esplicita
salva la Booking reale (conferma_itinerario_finale).

Lo stato dell'itinerario "in lavorazione" (non ancora confermato) vive in
Conversation.pending_itinerary (vedi chat/models.py) - i tool di
sostituzione/conferma lo leggono e lo aggiornano, perché l'LLM da solo non
può/deve tenere traccia in modo affidabile di quali componenti sono già
stati accettati dall'utente.

Ogni tool qui definito ha:
- una TOOL DEFINITION (dict in formato neutro, vedi chat/llm/base.py) che
  viene mostrata all'LLM così sa quando e come invocarlo;
- una funzione di ESECUZIONE corrispondente. I tool che operano su uno stato
  di conversazione (sostituzioni, conferma finale) accettano `conversation`
  come primo argomento, gestito da execute_tool - vedi sotto.

Il dizionario TOOL_DEFINITIONS/TOOL_EXECUTORS in fondo al file raccoglie
tutto in un unico punto da cui l'orchestratore legge sia le definizioni da
passare al modello sia le funzioni da eseguire.
"""
from decimal import Decimal, InvalidOperation

from catalog.models import Country, ActivityCategory
from catalog.rag.search import search_activities_semantic
from bookings.engine.itinerary_generator import (
    generate_itinerary, find_alternative_activity, find_alternative_hotel,
)


# ---------------------------------------------------------------------------
# Tool 1: estrai_requisiti_viaggio
#
# Non esegue nessuna query: è un tool "strutturale", usato per far sì che
# l'LLM produca un output a schema fisso non appena ritiene di avere
# raccolto tutti i dati necessari dalla conversazione naturale con l'utente.
# L'orchestratore intercetta questa specifica tool call per decidere se è
# il momento di passare alla generazione dell'itinerario.
# ---------------------------------------------------------------------------

ESTRAI_REQUISITI_TOOL = {
    "name": "estrai_requisiti_viaggio",
    "description": (
        "Registra i requisiti di viaggio raccolti finora dalla conversazione "
        "con l'utente. Usa questo tool non appena hai raccolto budget, "
        "nazione di interesse, mese di viaggio e almeno una preferenza di "
        "attività. Se manca ancora un dato, continua a chiedere all'utente "
        "invece di usare questo tool con valori inventati o nulli."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "budget_totale": {
                "type": "number",
                "description": "Budget totale disponibile per il viaggio, in euro.",
            },
            "nazione": {
                "type": "string",
                "description": "Nazione di destinazione indicata dall'utente (es. 'Italia', 'Francia').",
            },
            "mese_viaggio": {
                "type": "integer",
                "description": "Mese del viaggio, come numero da 1 (gennaio) a 12 (dicembre).",
            },
            "preferenze_attivita": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Categorie di attività preferite indicate dall'utente, in linguaggio "
                    "libero (es. ['cultura', 'relax']). Verranno poi mappate alle categorie "
                    "disponibili nel sistema."
                ),
            },
        },
        "required": ["budget_totale", "nazione", "mese_viaggio", "preferenze_attivita"],
    },
}


def esegui_estrai_requisiti_viaggio(budget_totale, nazione, mese_viaggio, preferenze_attivita) -> dict:
    """
    Valida e normalizza i requisiti estratti dalla conversazione, risolvendo
    il nome della nazione e delle preferenze ai rispettivi ID/slug nel
    database. Non genera ancora l'itinerario: si limita a confermare che i
    dati sono validi e risolvibili, così l'LLM/orchestratore può procedere
    con sicurezza al passo successivo (chiamata a genera_itinerario).
    """
    errors = []

    try:
        budget = Decimal(str(budget_totale))
        if budget <= 0:
            errors.append("Il budget deve essere un numero positivo.")
    except (InvalidOperation, TypeError, ValueError):
        budget = None
        errors.append(f"Budget non valido: '{budget_totale}'.")

    country = Country.objects.filter(name__iexact=str(nazione).strip()).first()
    if not country:
        available = ", ".join(Country.objects.values_list('name', flat=True))
        errors.append(
            f"Nazione '{nazione}' non trovata nel catalogo. Nazioni disponibili: {available}."
        )

    try:
        month = int(mese_viaggio)
        if not (1 <= month <= 12):
            errors.append("Il mese deve essere un numero tra 1 e 12.")
            month = None
    except (TypeError, ValueError):
        month = None
        errors.append(f"Mese non valido: '{mese_viaggio}'.")

    # Le preferenze sono testo libero dell'utente: proviamo a mappare ogni
    # voce a uno slug di categoria esistente (case-insensitive, match parziale),
    # ma non è un errore bloccante se qualcuna non corrisponde - verrà comunque
    # usata come query testuale per il RAG nel motore di generazione.
    resolved_preferences = []
    unmatched_preferences = []
    all_categories = {c.name.lower(): c.slug for c in ActivityCategory.objects.all()}
    for pref in (preferenze_attivita or []):
        pref_lower = str(pref).strip().lower()
        matched_slug = all_categories.get(pref_lower)
        if not matched_slug:
            # match parziale (es. "culturale" -> "cultura")
            for cat_name, slug in all_categories.items():
                if pref_lower in cat_name or cat_name in pref_lower:
                    matched_slug = slug
                    break
        if matched_slug:
            resolved_preferences.append(matched_slug)
        else:
            unmatched_preferences.append(pref)

    if errors:
        return {"valido": False, "errori": errors}

    return {
        "valido": True,
        "budget_totale": str(budget),
        "nazione": country.name,
        "nazione_id": country.id,
        "mese_viaggio": month,
        "preferenze_riconosciute": resolved_preferences,
        "preferenze_non_riconosciute": unmatched_preferences,
        "messaggio": (
            "Requisiti validi e pronti per la generazione dell'itinerario."
            if not unmatched_preferences else
            f"Requisiti validi. Nota: le preferenze {unmatched_preferences} non "
            "corrispondono a categorie esatte ma verranno comunque considerate "
            "nella ricerca semantica delle attività."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 2: genera_itinerario
#
# Invoca il motore deterministico (bookings/engine/itinerary_generator.py).
# Va chiamato SOLO dopo che estrai_requisiti_viaggio ha confermato dati validi.
# ---------------------------------------------------------------------------

GENERA_ITINERARIO_TOOL = {
    "name": "genera_itinerario",
    "description": (
        "Genera una PROPOSTA di itinerario di viaggio (volo andata/ritorno, hotel per "
        "ogni notte, un'attività per ogni giorno) che rispetta il budget e la "
        "disponibilità reale. Chiama questo tool solo dopo aver raccolto e "
        "validato tutti i requisiti con estrai_requisiti_viaggio. Se il risultato "
        "ha successo=false, spiega all'utente il motivo (riportato nel campo "
        "'motivo') e proponi di modificare un vincolo (es. aumentare il budget "
        "o cambiare mese). Se ha successo, presenta l'itinerario giorno per "
        "giorno e chiedi all'utente se ogni componente (hotel, attività di "
        "ciascun giorno) gli piace o se vuole un'alternativa: NON è ancora "
        "prenotato, è solo una proposta da rivedere insieme (vedi "
        "sostituisci_attivita_giorno, sostituisci_hotel, conferma_itinerario_finale)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nazione": {
                "type": "string",
                "description": "Nome della nazione di destinazione, come confermato da estrai_requisiti_viaggio.",
            },
            "budget_totale": {
                "type": "number",
                "description": "Budget totale disponibile, in euro.",
            },
            "mese_viaggio": {
                "type": "integer",
                "description": "Mese del viaggio (1-12).",
            },
            "preferenze_attivita": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Categorie/preferenze di attività da privilegiare nella selezione.",
            },
        },
        "required": ["nazione", "budget_totale", "mese_viaggio", "preferenze_attivita"],
    },
}


def esegui_genera_itinerario(conversation, nazione, budget_totale, mese_viaggio, preferenze_attivita) -> dict:
    """
    Risolve la nazione a ID e chiama il motore di generazione itinerario.
    Se la generazione ha successo, salva lo stato in
    conversation.pending_itinerary (ogni componente con approvato=False,
    in attesa di revisione dall'utente) - è il punto di partenza del
    flusso di revisione interattiva gestito dagli altri tool di questo file.
    """
    country = Country.objects.filter(name__iexact=str(nazione).strip()).first()
    if not country:
        return {
            "successo": False,
            "motivo": f"Nazione '{nazione}' non trovata nel catalogo.",
        }

    try:
        budget = Decimal(str(budget_totale))
    except (InvalidOperation, TypeError, ValueError):
        return {"successo": False, "motivo": f"Budget non valido: '{budget_totale}'."}

    try:
        month = int(mese_viaggio)
    except (TypeError, ValueError):
        return {"successo": False, "motivo": f"Mese non valido: '{mese_viaggio}'."}

    # Le preferenze qui possono essere sia slug di categoria che testo libero:
    # il motore le usa per il filtro categoria (se corrispondono) e comunque
    # per il ranking semantico RAG, quindi non serve normalizzarle di nuovo.
    preferences = [str(p).strip().lower() for p in (preferenze_attivita or [])]

    result = generate_itinerary(
        country_id=country.id,
        total_budget=budget,
        travel_month=month,
        activity_preferences=preferences,
    )

    result_dict = result.to_dict()
    is_success = result_dict.pop("success")

    if not is_success:
        return {"successo": False, "motivo": result_dict.pop("reason", "Itinerario non generabile.")}

    # Ogni componente parte come non approvato: l'utente deve poter rivedere
    # e contestare singolarmente hotel e ogni attività giornaliera.
    for stay in result_dict["hotel_stays"]:
        stay["approvato"] = False
    for activity in result_dict["daily_activities"]:
        activity["approvato"] = False

    conversation.pending_itinerary = {
        "country_id": country.id,
        "city_id": result.outbound_flight.arrival_airport.city_id,
        "total_budget": str(budget),
        "preferenze_attivita": preferences,
        **result_dict,
    }
    conversation.save(update_fields=["pending_itinerary"])

    return {"successo": True, **result_dict}


# ---------------------------------------------------------------------------
# Tool 3: cerca_attivita
#
# Espone la ricerca RAG/filtrata sulle attività come tool indipendente, per
# i casi in cui l'utente vuole esplorare alternative prima/dopo la
# generazione dell'itinerario completo (es. "mostrami altre attività a Roma
# legate al cibo").
# ---------------------------------------------------------------------------

CERCA_ATTIVITA_TOOL = {
    "name": "cerca_attivita",
    "description": (
        "Cerca attività turistiche disponibili in base a una descrizione testuale "
        "libera e, opzionalmente, una città o nazione. Utile quando l'utente "
        "vuole esplorare alternative o avere più dettagli su cosa fare, anche "
        "senza generare un itinerario completo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "descrizione_ricerca": {
                "type": "string",
                "description": "Cosa sta cercando l'utente, in linguaggio naturale (es. 'qualcosa di rilassante per famiglie').",
            },
            "nazione": {
                "type": "string",
                "description": "Nazione in cui cercare (opzionale).",
            },
            "citta": {
                "type": "string",
                "description": "Città in cui cercare (opzionale, ha priorità su nazione se entrambe fornite).",
            },
            "max_risultati": {
                "type": "integer",
                "description": "Numero massimo di risultati da restituire (default 5).",
            },
        },
        "required": ["descrizione_ricerca"],
    },
}


def esegui_cerca_attivita(descrizione_ricerca, nazione=None, citta=None, max_risultati=5) -> dict:
    """Esegue la ricerca semantica sulle attività, con filtro opzionale per città/nazione."""
    from catalog.models import Activity

    queryset = Activity.objects.all()
    if citta:
        queryset = queryset.filter(city__name__iexact=str(citta).strip())
    elif nazione:
        queryset = queryset.filter(city__country__name__iexact=str(nazione).strip())

    if not queryset.exists():
        return {
            "risultati": [],
            "messaggio": "Nessuna attività trovata per i filtri di città/nazione indicati.",
        }

    top_k = int(max_risultati) if max_risultati else 5
    ranked = search_activities_semantic(descrizione_ricerca, queryset=queryset, top_k=top_k)

    return {
        "risultati": [
            {
                "id": activity.id,
                "nome": activity.name,
                "citta": activity.city.name,
                "categoria": activity.category.name,
                "descrizione": activity.description,
                "prezzo_base": str(activity.base_price),
            }
            for activity in ranked
        ]
    }


# ---------------------------------------------------------------------------
# Tool 4: sostituisci_attivita_giorno
#
# Parte del flusso di revisione interattiva: l'utente non è soddisfatto
# dell'attività proposta per un giorno specifico. Cerca un'alternativa
# usando il margine di budget residuo di TUTTO l'itinerario (deciso
# insieme), e aggiorna lo stato in pending_itinerary se trovata.
# ---------------------------------------------------------------------------

SOSTITUISCI_ATTIVITA_TOOL = {
    "name": "sostituisci_attivita_giorno",
    "description": (
        "Sostituisce l'attività proposta per un giorno specifico dell'itinerario "
        "in revisione, perché l'utente ha detto di non esserne soddisfatto. "
        "Cerca un'alternativa usando il budget residuo di tutto l'itinerario. "
        "Usa questo tool solo dopo che è già stato generato un itinerario con "
        "genera_itinerario. Se non si trova un'alternativa entro budget, spiega "
        "il motivo all'utente."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "Data (formato YYYY-MM-DD) del giorno di cui sostituire l'attività, come mostrata nell'itinerario proposto.",
            },
            "note_preferenza": {
                "type": "string",
                "description": "Eventuale indicazione dell'utente su cosa preferirebbe invece (es. 'qualcosa più economico', 'preferirei sport'). Opzionale.",
            },
        },
        "required": ["data"],
    },
}


def esegui_sostituisci_attivita_giorno(conversation, data, note_preferenza=None) -> dict:
    """
    Trova un'alternativa per l'attività del giorno indicato, nel margine di
    budget residuo di tutto l'itinerario in revisione, e aggiorna
    conversation.pending_itinerary se trovata.
    """
    from datetime import date as date_cls

    pending = conversation.pending_itinerary
    if not pending:
        return {"successo": False, "motivo": "Non c'è ancora nessun itinerario generato da modificare."}

    try:
        target_date = date_cls.fromisoformat(str(data))
    except ValueError:
        return {"successo": False, "motivo": f"Data non valida: '{data}'. Usa il formato YYYY-MM-DD."}

    daily_activities = pending.get("daily_activities", [])
    current_entry = next((a for a in daily_activities if a["date"] == data), None)
    if not current_entry:
        return {"successo": False, "motivo": f"Nessuna attività trovata per la data {data} nell'itinerario corrente."}

    # Margine residuo = budget totale - tutto quello già allocato (voli, hotel,
    # e le altre attività diverse da quella che stiamo per sostituire).
    spent_elsewhere = (
        Decimal(pending["outbound_flight"]["price"]) + Decimal(pending["return_flight"]["price"])
        + sum(Decimal(s["price_per_night"]) for s in pending.get("hotel_stays", []))
        + sum(Decimal(a["price"]) for a in daily_activities if a["date"] != data)
    )
    remaining_budget = Decimal(pending["total_budget"]) - spent_elsewhere

    preferences = list(pending.get("preferenze_attivita", []))
    if note_preferenza:
        preferences.append(str(note_preferenza).strip().lower())

    alternative = find_alternative_activity(
        city_id=pending["city_id"],
        day=target_date,
        max_budget=remaining_budget,
        preferences=preferences,
        exclude_activity_id=current_entry["activity_id"],
    )

    if not alternative:
        return {
            "successo": False,
            "motivo": (
                f"Nessuna alternativa disponibile per il {data} entro il budget residuo "
                f"({remaining_budget}€)."
            ),
        }

    new_entry = {
        "activity_id": alternative["activity"].id,
        "activity_name": alternative["activity"].name,
        "date": data,
        "price": str(alternative["price"]),
        "approvato": False,
    }
    # Sostituiamo l'entry corrispondente nella lista, mantenendo l'ordine
    pending["daily_activities"] = [
        new_entry if a["date"] == data else a for a in daily_activities
    ]
    # Ricalcoliamo il costo totale dell'itinerario per coerenza
    pending["total_cost"] = str(
        Decimal(pending["outbound_flight"]["price"]) + Decimal(pending["return_flight"]["price"])
        + sum(Decimal(s["price_per_night"]) for s in pending.get("hotel_stays", []))
        + sum(Decimal(a["price"]) for a in pending["daily_activities"])
    )
    conversation.pending_itinerary = pending
    conversation.save(update_fields=["pending_itinerary"])

    return {"successo": True, "nuova_attivita": new_entry, "costo_totale_itinerario": pending["total_cost"]}


# ---------------------------------------------------------------------------
# Tool 5: sostituisci_hotel
#
# Equivalente di sostituisci_attivita_giorno, ma per l'hotel (tutte le notti
# insieme, dato che nel motore è un'unica struttura per tutto il soggiorno).
# ---------------------------------------------------------------------------

SOSTITUISCI_HOTEL_TOOL = {
    "name": "sostituisci_hotel",
    "description": (
        "Sostituisce l'hotel proposto nell'itinerario in revisione (per tutte le "
        "notti del soggiorno), perché l'utente ha detto di non esserne "
        "soddisfatto (es. troppo caro, vuole più stelle, posizione diversa). "
        "Cerca un'alternativa usando il budget residuo di tutto l'itinerario. "
        "Usa questo tool solo dopo che è già stato generato un itinerario con "
        "genera_itinerario."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "note_preferenza": {
                "type": "string",
                "description": "Eventuale indicazione dell'utente su cosa preferirebbe invece. Opzionale.",
            },
        },
        "required": [],
    },
}


def esegui_sostituisci_hotel(conversation, note_preferenza=None) -> dict:
    """
    Trova un hotel alternativo per tutte le notti del soggiorno, nel margine
    di budget residuo di tutto l'itinerario, e aggiorna pending_itinerary.
    """
    from datetime import date as date_cls

    pending = conversation.pending_itinerary
    if not pending:
        return {"successo": False, "motivo": "Non c'è ancora nessun itinerario generato da modificare."}

    hotel_stays = pending.get("hotel_stays", [])
    if not hotel_stays:
        return {"successo": False, "motivo": "Nessun hotel trovato nell'itinerario corrente."}

    current_hotel_id = hotel_stays[0]["hotel_id"]
    nights_dates = [date_cls.fromisoformat(s["date"]) for s in hotel_stays]

    spent_elsewhere = (
        Decimal(pending["outbound_flight"]["price"]) + Decimal(pending["return_flight"]["price"])
        + sum(Decimal(a["price"]) for a in pending.get("daily_activities", []))
    )
    remaining_budget = Decimal(pending["total_budget"]) - spent_elsewhere

    alternative = find_alternative_hotel(
        city_id=pending["city_id"],
        nights_dates=nights_dates,
        max_total_budget=remaining_budget,
        exclude_hotel_id=current_hotel_id,
    )

    if not alternative:
        return {
            "successo": False,
            "motivo": f"Nessun hotel alternativo disponibile per tutte le notti entro il budget residuo ({remaining_budget}€).",
        }

    new_stays = [
        {
            "hotel_id": stay["hotel"].id,
            "hotel_name": stay["hotel"].name,
            "date": stay["date"].isoformat(),
            "price_per_night": str(stay["price"]),
            "approvato": False,
        }
        for stay in alternative["stays"]
    ]
    pending["hotel_stays"] = new_stays
    pending["total_cost"] = str(
        Decimal(pending["outbound_flight"]["price"]) + Decimal(pending["return_flight"]["price"])
        + sum(Decimal(s["price_per_night"]) for s in new_stays)
        + sum(Decimal(a["price"]) for a in pending.get("daily_activities", []))
    )
    conversation.pending_itinerary = pending
    conversation.save(update_fields=["pending_itinerary"])

    return {"successo": True, "nuovo_hotel": new_stays, "costo_totale_itinerario": pending["total_cost"]}


# ---------------------------------------------------------------------------
# Tool 6: conferma_itinerario_finale
#
# Trigger esplicito per salvare la Booking reale. Va invocato SOLO quando
# l'utente ha confermato di essere soddisfatto di OGNI componente
# dell'itinerario in revisione (non prima). Crea la Booking in stato
# 'draft' e collega la Conversation, poi svuota pending_itinerary.
# ---------------------------------------------------------------------------

CONFERMA_ITINERARIO_TOOL = {
    "name": "conferma_itinerario_finale",
    "description": (
        "Salva l'itinerario in revisione come prenotazione effettiva. Usa "
        "questo tool SOLO dopo che l'utente ha esplicitamente confermato di "
        "essere soddisfatto di TUTTI i componenti dell'itinerario (voli, "
        "hotel, ogni attività giornaliera) - non chiamarlo se l'utente ha "
        "ancora dei dubbi o vuole vedere altre alternative. Se l'utente ha "
        "menzionato modifiche non ancora applicate, applicale prima con gli "
        "altri tool di sostituzione e richiedi conferma."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def esegui_conferma_itinerario_finale(conversation) -> dict:
    """
    Crea la Booking reale (stato 'draft', come da modello esistente - resta
    comunque disponibile l'azione 'confirm' su BookingViewSet se si vuole un
    ulteriore passaggio di conferma lato API/frontend) a partire dallo stato
    in pending_itinerary, poi lo svuota (la revisione è conclusa).
    """
    from datetime import date as date_cls
    from bookings.models import Booking, BookingFlight, BookingHotelStay, BookingActivity

    pending = conversation.pending_itinerary
    if not pending:
        return {"successo": False, "motivo": "Non c'è nessun itinerario in revisione da confermare."}

    booking = Booking.objects.create(
        user=conversation.user,
        country_id=pending["country_id"],
        total_budget=Decimal(pending["total_budget"]),
        requested_activity_preferences=pending.get("preferenze_attivita", []),
        travel_month=date_cls.fromisoformat(pending["outbound_flight"]["departure_datetime"][:10]).month,
        status=Booking.Status.DRAFT,
    )

    BookingFlight.objects.create(
        booking=booking,
        flight_id=pending["outbound_flight"]["id"],
        direction=BookingFlight.Direction.OUTBOUND,
        price=Decimal(pending["outbound_flight"]["price"]),
    )
    BookingFlight.objects.create(
        booking=booking,
        flight_id=pending["return_flight"]["id"],
        direction=BookingFlight.Direction.RETURN,
        price=Decimal(pending["return_flight"]["price"]),
    )
    for stay in pending.get("hotel_stays", []):
        BookingHotelStay.objects.create(
            booking=booking,
            hotel_id=stay["hotel_id"],
            date=date_cls.fromisoformat(stay["date"]),
            price_per_night=Decimal(stay["price_per_night"]),
        )
    for activity in pending.get("daily_activities", []):
        BookingActivity.objects.create(
            booking=booking,
            activity_id=activity["activity_id"],
            date=date_cls.fromisoformat(activity["date"]),
            price=Decimal(activity["price"]),
        )

    conversation.booking = booking
    conversation.pending_itinerary = {}
    conversation.save(update_fields=["booking", "pending_itinerary"])

    return {
        "successo": True,
        "booking_id": booking.id,
        "stato": booking.status,
        "costo_totale": str(booking.total_cost),
        "messaggio": "Itinerario salvato come prenotazione. L'utente potrà confermarla definitivamente dalla sua dashboard.",
    }


# ---------------------------------------------------------------------------
# Registro centrale dei tool: definizioni (da passare all'LLM) + funzioni
# di esecuzione (da invocare quando l'LLM richiede una tool call).
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    ESTRAI_REQUISITI_TOOL,
    GENERA_ITINERARIO_TOOL,
    CERCA_ATTIVITA_TOOL,
    SOSTITUISCI_ATTIVITA_TOOL,
    SOSTITUISCI_HOTEL_TOOL,
    CONFERMA_ITINERARIO_TOOL,
]

TOOL_EXECUTORS = {
    "estrai_requisiti_viaggio": esegui_estrai_requisiti_viaggio,
    "genera_itinerario": esegui_genera_itinerario,
    "cerca_attivita": esegui_cerca_attivita,
    "sostituisci_attivita_giorno": esegui_sostituisci_attivita_giorno,
    "sostituisci_hotel": esegui_sostituisci_hotel,
    "conferma_itinerario_finale": esegui_conferma_itinerario_finale,
}

# Tool che operano sullo stato della conversazione (itinerario in revisione)
# e quindi richiedono l'oggetto Conversation come primo argomento, gestito
# direttamente da execute_tool - l'LLM non lo passa né lo vede tra i
# parametri (non è nella tool definition sopra).
TOOLS_REQUIRING_CONVERSATION = {
    "genera_itinerario",
    "sostituisci_attivita_giorno",
    "sostituisci_hotel",
    "conferma_itinerario_finale",
}


def execute_tool(name: str, arguments: dict, conversation=None) -> dict:
    """
    Punto di ingresso unico per eseguire un tool dato il nome (come richiesto
    dall'LLM) e i relativi argomenti. Usato dall'orchestratore per non dover
    conoscere i dettagli di ciascun tool.

    Per i tool che operano sullo stato dell'itinerario in revisione
    (TOOLS_REQUIRING_CONVERSATION), `conversation` viene passato come primo
    argomento posizionale aggiuntivo - l'orchestratore deve sempre fornirlo
    quando esegue uno di questi tool.
    """
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        return {"errore": f"Tool '{name}' non riconosciuto."}

    try:
        if name in TOOLS_REQUIRING_CONVERSATION:
            if conversation is None:
                return {"errore": f"Tool '{name}' richiede una conversazione attiva, non fornita."}
            return executor(conversation, **arguments)
        return executor(**arguments)
    except TypeError as e:
        return {"errore": f"Argomenti non validi per il tool '{name}': {e}"}
