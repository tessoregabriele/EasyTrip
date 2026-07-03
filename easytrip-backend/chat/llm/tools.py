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
    generate_itinerary, find_alternative_activity, find_alternative_hotel, find_alternative_flight,
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
        "nazione di interesse, mese di viaggio, durata del soggiorno e almeno "
        "una preferenza di attività. Se manca ancora un dato - inclusa la "
        "durata del viaggio, che l'utente potrebbe esprimere in modo implicito "
        "(es. 'una settimana', 'un weekend') - continua a chiedere all'utente "
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
            "durata_soggiorno_notti": {
                "type": "integer",
                "description": (
                    "Durata del soggiorno richiesta dall'utente, espressa in numero di NOTTI. "
                    "Converti le espressioni in linguaggio naturale in un numero: 'un weekend' -> 2, "
                    "'una settimana' -> 7, 'dieci giorni' -> 9 (giorni - 1 notte), 'due settimane' -> 14. "
                    "Se l'utente non ha ancora indicato una durata, chiediglielo esplicitamente invece "
                    "di indovinare: è un dato importante quanto il budget o il mese."
                ),
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
        "required": ["budget_totale", "nazione", "mese_viaggio", "durata_soggiorno_notti", "preferenze_attivita"],
    },
}


def esegui_estrai_requisiti_viaggio(budget_totale, nazione, mese_viaggio, durata_soggiorno_notti, preferenze_attivita) -> dict:
    """
    Valida e normalizza i requisiti estratti dalla conversazione, risolvendo
    il nome della nazione e delle preferenze ai rispettivi ID/slug nel
    database. Non genera ancora l'itinerario: si limita a confermare che i
    dati sono validi e risolvibili, così l'LLM/orchestratore può procedere
    con sicurezza al passo successivo (chiamata a genera_itinerario).
    """
    # Nota: budget_totale/nazione/mese_viaggio/durata_soggiorno_notti/preferenze_attivita
    # possono arrivare a None: il modello a volte chiama questo tool prima di aver
    # raccolto tutti i dati (vedi tipi "nullable" in ESTRAI_REQUISITI_TOOL). Li
    # trattiamo come "dato mancante" con un messaggio dedicato, invece di un
    # generico errore di parsing, così l'LLM capisce subito cosa chiedere ancora.
    errors = []

    if budget_totale is None:
        budget = None
        errors.append("Manca il budget totale: chiedilo all'utente.")
    else:
        try:
            budget = Decimal(str(budget_totale))
            if budget <= 0:
                errors.append("Il budget deve essere un numero positivo.")
        except (InvalidOperation, TypeError, ValueError):
            budget = None
            errors.append(f"Budget non valido: '{budget_totale}'.")

    if nazione is None:
        country = None
        errors.append("Manca la nazione di destinazione: chiedila all'utente.")
    else:
        country = Country.objects.filter(name__iexact=str(nazione).strip()).first()
        if not country:
            available = ", ".join(Country.objects.values_list('name', flat=True))
            errors.append(
                f"Nazione '{nazione}' non trovata nel catalogo. Nazioni disponibili: {available}."
            )

    if mese_viaggio is None:
        month = None
        errors.append("Manca il mese del viaggio: chiedilo all'utente.")
    else:
        try:
            month = int(mese_viaggio)
            if not (1 <= month <= 12):
                errors.append("Il mese deve essere un numero tra 1 e 12.")
                month = None
        except (TypeError, ValueError):
            month = None
            errors.append(f"Mese non valido: '{mese_viaggio}'.")

    if durata_soggiorno_notti is None:
        nights = None
        errors.append("Manca la durata del soggiorno: chiedila all'utente (in notti o giorni).")
    else:
        try:
            nights = int(durata_soggiorno_notti)
            if not (1 <= nights <= 60):
                errors.append("La durata del soggiorno deve essere un numero di notti tra 1 e 60.")
                nights = None
        except (TypeError, ValueError):
            nights = None
            errors.append(f"Durata del soggiorno non valida: '{durata_soggiorno_notti}'.")

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
        "durata_soggiorno_notti": nights,
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
            "durata_soggiorno_notti": {
                "type": "integer",
                "description": (
                    "Durata del soggiorno in NOTTI, come confermata da estrai_requisiti_viaggio "
                    "(es. 'una settimana' -> 7). Il motore sceglierà il volo di ritorno disponibile "
                    "più vicino possibile a questa durata."
                ),
            },
            "preferenze_attivita": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Categorie/preferenze di attività da privilegiare nella selezione.",
            },
        },
        "required": ["nazione", "budget_totale", "mese_viaggio", "durata_soggiorno_notti", "preferenze_attivita"],
    },
}


_MONTH_NAMES_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def _format_duration_label(nights: int) -> str:
    """
    Converte un numero di notti in un'espressione naturale in italiano, usata
    per il titolo automatico della conversazione (es. 7 notti -> 'una
    settimana', 2 notti -> 'un weekend'). È l'inverso della conversione che
    chiediamo all'LLM nelle tool definition qui sopra.
    """
    if nights <= 2:
        return "un weekend"
    if nights % 7 == 0:
        weeks = nights // 7
        return "una settimana" if weeks == 1 else f"{weeks} settimane"
    return f"{nights + 1} giorni"  # giorni di viaggio = notti + 1, più naturale per l'utente


def _build_conversation_title(city_name: str, month: int, nights: int) -> str:
    return f"{_format_duration_label(nights)} a {city_name} a {_MONTH_NAMES_IT[month - 1]}"


def esegui_genera_itinerario(conversation, nazione, budget_totale, mese_viaggio, durata_soggiorno_notti, preferenze_attivita) -> dict:
    """
    Risolve la nazione a ID e chiama il motore di generazione itinerario.
    Se la generazione ha successo, salva lo stato in
    conversation.pending_itinerary (ogni componente con approvato=False,
    in attesa di revisione dall'utente) - è il punto di partenza del
    flusso di revisione interattiva gestito dagli altri tool di questo file.
    """
    from datetime import date as date_cls

    # Come in esegui_estrai_requisiti_viaggio, ogni valore può arrivare a None
    # se il modello chiama questo tool con dati incompleti: gestiamo il caso
    # esplicitamente invece di lasciare che un errore di parsing generico
    # nasconda che si tratta semplicemente di un dato mancante.
    if nazione is None:
        return {"successo": False, "motivo": "Manca la nazione di destinazione: chiedila all'utente."}
    country = Country.objects.filter(name__iexact=str(nazione).strip()).first()
    if not country:
        return {
            "successo": False,
            "motivo": f"Nazione '{nazione}' non trovata nel catalogo.",
        }

    if budget_totale is None:
        return {"successo": False, "motivo": "Manca il budget totale: chiedilo all'utente."}
    try:
        budget = Decimal(str(budget_totale))
    except (InvalidOperation, TypeError, ValueError):
        return {"successo": False, "motivo": f"Budget non valido: '{budget_totale}'."}

    if mese_viaggio is None:
        return {"successo": False, "motivo": "Manca il mese del viaggio: chiedilo all'utente."}
    try:
        month = int(mese_viaggio)
    except (TypeError, ValueError):
        return {"successo": False, "motivo": f"Mese non valido: '{mese_viaggio}'."}

    if durata_soggiorno_notti is None:
        return {"successo": False, "motivo": "Manca la durata del soggiorno: chiedila all'utente."}
    try:
        nights = int(durata_soggiorno_notti)
        if not (1 <= nights <= 60):
            return {"successo": False, "motivo": "La durata del soggiorno deve essere un numero di notti tra 1 e 60."}
    except (TypeError, ValueError):
        return {"successo": False, "motivo": f"Durata del soggiorno non valida: '{durata_soggiorno_notti}'."}

    # Le preferenze qui possono essere sia slug di categoria che testo libero:
    # il motore le usa per il filtro categoria (se corrispondono) e comunque
    # per il ranking semantico RAG, quindi non serve normalizzarle di nuovo.
    preferences = [str(p).strip().lower() for p in (preferenze_attivita or [])]

    result = generate_itinerary(
        country_id=country.id,
        total_budget=budget,
        travel_month=month,
        activity_preferences=preferences,
        requested_nights=nights,
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
    # Il titolo riflette il viaggio effettivamente generato (durata reale e
    # città di destinazione scelta dal motore), non solo quanto richiesto -
    # è più utile per riconoscere la conversazione nello storico.
    checkin = date_cls.fromisoformat(result_dict["outbound_flight"]["arrival_datetime"][:10])
    checkout = date_cls.fromisoformat(result_dict["return_flight"]["departure_datetime"][:10])
    conversation.title = _build_conversation_title(
        city_name=result.outbound_flight.arrival_airport.city.name,
        month=checkin.month,
        nights=(checkout - checkin).days,
    )
    conversation.save(update_fields=["pending_itinerary", "title"])

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
            "consenti_doppioni": {
                "type": "boolean",
                "description": (
                    "Di default false: l'alternativa trovata non ripeterà mai un'attività già "
                    "presente in un altro giorno dell'itinerario. Imposta a true SOLO se l'utente "
                    "ha esplicitamente chiesto di poter ripetere/riproporre un'attività già usata "
                    "altrove (es. 'va bene anche se è uguale a un altro giorno', 'voglio rifare "
                    "quella stessa cosa')."
                ),
            },
        },
        "required": ["data"],
    },
}


def esegui_sostituisci_attivita_giorno(conversation, data, note_preferenza=None, consenti_doppioni=False) -> dict:
    """
    Trova un'alternativa per l'attività del giorno indicato, nel margine di
    budget residuo di tutto l'itinerario in revisione, e aggiorna
    conversation.pending_itinerary se trovata. Per default evita di
    riproporre un'attività già usata in un altro giorno dell'itinerario
    (consenti_doppioni=True disattiva questa esclusione, su richiesta esplicita
    dell'utente).
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

    # Escludiamo di default anche le attività già usate negli altri giorni,
    # per non introdurre un doppione non richiesto durante una sostituzione.
    other_days_activity_ids = [a["activity_id"] for a in daily_activities if a["date"] != data]

    alternative = find_alternative_activity(
        city_id=pending["city_id"],
        day=target_date,
        max_budget=remaining_budget,
        preferences=preferences,
        exclude_activity_id=current_entry["activity_id"],
        exclude_activity_ids=None if consenti_doppioni else other_days_activity_ids,
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
        "altri tool di sostituzione e richiedi conferma.\n\n"
        "Il tool ricontrolla la disponibilità reale di ogni componente prima "
        "di confermare (potrebbe essere passato del tempo dalla proposta "
        "iniziale). Se il risultato ha successo=true ma prenotato=false, "
        "significa che qualcosa non era più disponibile ed è stato sostituito "
        "(o rimosso, per le attività) - presenta all'utente le modifiche "
        "elencate in problemi_disponibilita e chiedi una NUOVA conferma "
        "esplicita prima di richiamare di nuovo questo tool. Solo quando "
        "prenotato=true la prenotazione è stata effettivamente salvata."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def esegui_conferma_itinerario_finale(conversation) -> dict:
    """
    Prima di confermare, ricontrolla la disponibilità REALE di ogni
    componente dell'itinerario in revisione (voli, hotel, attività): può
    essere passato del tempo dalla proposta iniziale (l'unico altro momento
    in cui la disponibilità viene controllata) e qualcosa potrebbe non
    essere più prenotabile nel frattempo.

    - Se tutto è ancora disponibile: decrementa l'inventario (posti/camere/
      spot) dentro una transazione con lock di riga, per evitare che due
      conferme concorrenti sovraprenotino la stessa risorsa, e crea la
      Booking reale (stato 'draft').
    - Se qualcosa NON è più disponibile: lo sostituisce con un'alternativa
      (o lo rimuove, solo per le attività giornaliere, se non se ne trova
      una - un itinerario senza attività per un giorno resta valido, come
      già tollerato dal motore di generazione iniziale) e aggiorna
      pending_itinerary con le nuove proposte, SENZA creare la Booking:
      l'utente deve rivedere/riapprovare le parti cambiate prima di poter
      richiamare questo tool con successo.
    """
    from datetime import date as date_cls
    from django.db import transaction
    from django.db.models import F
    from catalog.models import Flight, HotelAvailability, ActivityAvailability
    from bookings.models import Booking, BookingFlight, BookingHotelStay, BookingActivity

    pending = conversation.pending_itinerary
    if not pending:
        return {"successo": False, "motivo": "Non c'è nessun itinerario in revisione da confermare."}

    with transaction.atomic():
        problems = []  # [{"componente", "motivo", "sostituito_con"}], vuoto se tutto è ancora disponibile

        # --- Voli: stessa tratta/data, non tocchiamo il resto dell'itinerario ---
        for direction, key, other_key in (
            ("andata", "outbound_flight", "return_flight"),
            ("ritorno", "return_flight", "outbound_flight"),
        ):
            flight_row = Flight.objects.select_for_update().get(id=pending[key]["id"])
            if flight_row.seats_available > 0:
                continue

            spent_elsewhere = (
                Decimal(pending[other_key]["price"])
                + sum(Decimal(s["price_per_night"]) for s in pending.get("hotel_stays", []))
                + sum(Decimal(a["price"]) for a in pending.get("daily_activities", []))
            )
            remaining_budget = Decimal(pending["total_budget"]) - spent_elsewhere

            alternative = find_alternative_flight(
                departure_airport_id=flight_row.departure_airport_id,
                arrival_airport_id=flight_row.arrival_airport_id,
                flight_date=flight_row.departure_datetime.date(),
                max_budget=remaining_budget,
                exclude_flight_id=flight_row.id,
            )

            if alternative:
                pending[key] = {
                    "id": alternative.id,
                    "flight_number": alternative.flight_number,
                    "departure_airport": alternative.departure_airport.iata_code,
                    "arrival_airport": alternative.arrival_airport.iata_code,
                    "departure_datetime": alternative.departure_datetime.isoformat(),
                    "arrival_datetime": alternative.arrival_datetime.isoformat(),
                    "price": str(alternative.price),
                }
                problems.append({
                    "componente": f"volo di {direction}",
                    "motivo": "Non più disponibile rispetto a quando era stato proposto.",
                    "sostituito_con": f"volo {alternative.flight_number} ({alternative.price}€)",
                })
            else:
                # Nessuna alternativa sulla stessa data/tratta: lasciamo il
                # volo originale nel draft (rimuoverlo renderebbe l'itinerario
                # incompleto) e segnaliamo il problema perché serve una
                # decisione dell'utente (es. cambiare mese o aumentare budget).
                problems.append({
                    "componente": f"volo di {direction}",
                    "motivo": "Non più disponibile e nessuna alternativa trovata sulla stessa data/tratta entro il budget.",
                    "sostituito_con": None,
                })

        # --- Hotel: un'unica struttura per tutte le notti del soggiorno ---
        hotel_stays = pending.get("hotel_stays", [])
        if hotel_stays:
            hotel_still_available = all(
                HotelAvailability.objects.select_for_update().get(
                    hotel_id=stay["hotel_id"], date=date_cls.fromisoformat(stay["date"]),
                ).rooms_available > 0
                for stay in hotel_stays
            )

            if not hotel_still_available:
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
                    exclude_hotel_id=hotel_stays[0]["hotel_id"],
                )

                if alternative:
                    pending["hotel_stays"] = [
                        {
                            "hotel_id": s["hotel"].id,
                            "hotel_name": s["hotel"].name,
                            "date": s["date"].isoformat(),
                            "price_per_night": str(s["price"]),
                            "approvato": False,
                        }
                        for s in alternative["stays"]
                    ]
                    problems.append({
                        "componente": "hotel",
                        "motivo": "Non più disponibile per tutte le notti richieste.",
                        "sostituito_con": alternative["hotel"].name,
                    })
                else:
                    problems.append({
                        "componente": "hotel",
                        "motivo": "Non più disponibile e nessuna alternativa trovata entro il budget.",
                        "sostituito_con": None,
                    })

        # --- Attività: una per giorno, rimozione ammessa se non si trova un'alternativa ---
        daily_activities = pending.get("daily_activities", [])
        updated_activities = []
        for activity_entry in daily_activities:
            row = ActivityAvailability.objects.select_for_update().get(
                activity_id=activity_entry["activity_id"], date=date_cls.fromisoformat(activity_entry["date"]),
            )
            if row.spots_available > 0:
                updated_activities.append(activity_entry)
                continue

            target_date = date_cls.fromisoformat(activity_entry["date"])
            other_days_activity_ids = [
                a["activity_id"] for a in daily_activities if a["date"] != activity_entry["date"]
            ]
            spent_elsewhere = (
                Decimal(pending["outbound_flight"]["price"]) + Decimal(pending["return_flight"]["price"])
                + sum(Decimal(s["price_per_night"]) for s in pending.get("hotel_stays", []))
                + sum(Decimal(a["price"]) for a in daily_activities if a["date"] != activity_entry["date"])
            )
            remaining_budget = Decimal(pending["total_budget"]) - spent_elsewhere

            alternative = find_alternative_activity(
                city_id=pending["city_id"],
                day=target_date,
                max_budget=remaining_budget,
                preferences=pending.get("preferenze_attivita", []),
                exclude_activity_id=activity_entry["activity_id"],
                exclude_activity_ids=other_days_activity_ids,
            )

            if alternative:
                updated_activities.append({
                    "activity_id": alternative["activity"].id,
                    "activity_name": alternative["activity"].name,
                    "date": activity_entry["date"],
                    "price": str(alternative["price"]),
                    "approvato": False,
                })
                problems.append({
                    "componente": f"attività del {activity_entry['date']}",
                    "motivo": "Non più disponibile rispetto a quando era stata proposta.",
                    "sostituito_con": alternative["activity"].name,
                })
            else:
                # Nessuna alternativa: rimuoviamo l'attività per quel giorno,
                # come già tollerato dal motore di generazione iniziale.
                problems.append({
                    "componente": f"attività del {activity_entry['date']}",
                    "motivo": "Non più disponibile e nessuna alternativa trovata entro il budget: rimossa per quel giorno.",
                    "sostituito_con": None,
                })

        pending["daily_activities"] = updated_activities
        pending["total_cost"] = str(
            Decimal(pending["outbound_flight"]["price"]) + Decimal(pending["return_flight"]["price"])
            + sum(Decimal(s["price_per_night"]) for s in pending.get("hotel_stays", []))
            + sum(Decimal(a["price"]) for a in pending["daily_activities"])
        )

        if problems:
            # Qualcosa non era più disponibile: aggiorniamo il draft con le
            # nuove proposte ma NON confermiamo la prenotazione in questo
            # giro - l'utente deve rivedere/approvare di nuovo le parti
            # cambiate prima che questo tool possa avere successo.
            conversation.pending_itinerary = pending
            conversation.save(update_fields=["pending_itinerary"])
            return {
                "successo": True,
                "prenotato": False,
                "problemi_disponibilita": problems,
                "itinerario_aggiornato": pending,
                "messaggio": (
                    "Alcuni componenti dell'itinerario non erano più disponibili rispetto a "
                    "quando erano stati proposti: sono stati sostituiti (o rimossi, se non è "
                    "stata trovata un'alternativa) come indicato in problemi_disponibilita. "
                    "Presenta le modifiche all'utente e chiedi una nuova conferma esplicita "
                    "prima di richiamare questo tool."
                ),
            }

        # --- Tutto ancora disponibile: decrementiamo l'inventario e creiamo la Booking reale ---
        Flight.objects.filter(id=pending["outbound_flight"]["id"]).update(seats_available=F("seats_available") - 1)
        Flight.objects.filter(id=pending["return_flight"]["id"]).update(seats_available=F("seats_available") - 1)
        for stay in pending.get("hotel_stays", []):
            HotelAvailability.objects.filter(
                hotel_id=stay["hotel_id"], date=date_cls.fromisoformat(stay["date"]),
            ).update(rooms_available=F("rooms_available") - 1)
        for activity in pending["daily_activities"]:
            ActivityAvailability.objects.filter(
                activity_id=activity["activity_id"], date=date_cls.fromisoformat(activity["date"]),
            ).update(spots_available=F("spots_available") - 1)

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
        for activity in pending["daily_activities"]:
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
        "prenotato": True,
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

    # Alcuni provider (Groq) restituiscono il letterale "null" come argomenti
    # per i tool senza parametri, che json.loads trasforma in None: senza
    # questo fallback **None solleverebbe un TypeError ad ogni chiamata.
    arguments = arguments or {}

    try:
        if name in TOOLS_REQUIRING_CONVERSATION:
            if conversation is None:
                return {"errore": f"Tool '{name}' richiede una conversazione attiva, non fornita."}
            return executor(conversation, **arguments)
        return executor(**arguments)
    except TypeError as e:
        return {"errore": f"Argomenti non validi per il tool '{name}': {e}"}
