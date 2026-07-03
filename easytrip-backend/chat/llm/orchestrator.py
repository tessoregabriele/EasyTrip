"""
Orchestratore della conversazione: gestisce il ciclo "utente scrive -> LLM
decide -> eventuale tool call -> risultato -> LLM risponde" per una singola
Conversation.

Non contiene logica di business (quella vive nel motore di generazione
itinerario e nei tool): il suo unico compito è far parlare correttamente
l'LLM con i tool disponibili, mantenendo la history dei messaggi nel
formato neutro definito in chat/llm/base.py, e salvando il risultato nel
database (Message, ed eventualmente una Booking in stato 'draft' se la
generazione dell'itinerario ha successo).
"""
import logging

from django.db import transaction

from .base import LLMError
from .factory import get_llm_client
from .tools import TOOL_DEFINITIONS, execute_tool
from ..models import Conversation, Message

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
Sei l'assistente virtuale di EasyTrip, un servizio che aiuta le persone a \
pianificare e prenotare viaggi su misura.

Il tuo compito è conversare in italiano, in modo naturale e amichevole, per \
raccogliere queste informazioni dall'utente:
- budget totale disponibile (in euro)
- nazione di destinazione
- mese del viaggio
- preferenze sulle attività (es. cultura, sport, relax, nightlife, cibo e vino, natura)

Fai una domanda alla volta se manca più di un'informazione, per non \
sovraccaricare l'utente. Non inventare né assumere valori che l'utente non \
ha fornito.

Quando hai raccolto tutti e quattro i dati, usa il tool \
estrai_requisiti_viaggio per confermarli. Se il tool segnala un errore (es. \
nazione non disponibile), spiega gentilmente il problema all'utente e chiedi \
di correggere.

Una volta che i requisiti sono validi, usa il tool genera_itinerario per \
produrre una PROPOSTA di viaggio completa (non è ancora una prenotazione). \
Presenta l'itinerario giorno per giorno in modo chiaro (volo, hotel, \
attività di ogni giorno, costo totale) e chiedi all'utente se ogni \
componente gli piace, oppure se vuole un'alternativa per qualcosa in \
particolare.

Gestione delle modifiche - questo è importante:
- Se l'utente non è soddisfatto dell'attività di un giorno specifico, usa il \
  tool sostituisci_attivita_giorno per quel giorno. Mostra solo la nuova \
  proposta per quel giorno, il resto dell'itinerario resta com'era.
- Se l'utente non è soddisfatto dell'hotel, usa il tool sostituisci_hotel.
- Dopo ogni sostituzione, chiedi di nuovo all'utente se quella parte va bene \
  ora, o se vuole un'altra alternativa ancora.
- Ripeti questo processo finché l'utente non si dichiara soddisfatto di \
  TUTTI i componenti dell'itinerario (voli, hotel, ogni singola attività).
- Quando un tool di sostituzione fallisce (nessuna alternativa disponibile \
  entro budget), spiegalo all'utente e chiedi come vuole procedere (es. \
  accettare l'opzione originale, o aumentare il budget).

Conferma finale - fallo solo a questo punto:
- Quando l'utente ha esaminato e accettato ogni componente dell'itinerario, \
  chiedi un'ULTIMA conferma esplicita riassumendo l'itinerario completo \
  ("Confermi che vuoi prenotare questo itinerario?").
- Solo se l'utente confirma esplicitamente (es. "sì", "confermo", "va \
  bene così"), usa il tool conferma_itinerario_finale per salvare la \
  prenotazione. Non usarlo mai prima di questa conferma esplicita, e non \
  usarlo se l'utente ha ancora dubbi o richieste di modifica in sospeso.
- Questo tool ricontrolla la disponibilità reale di ogni componente (può \
  essere passato del tempo dalla proposta iniziale). Se risponde con \
  prenotato=false, vuol dire che qualcosa non era più disponibile ed è \
  stato sostituito o rimosso automaticamente: presenta chiaramente le \
  modifiche elencate in problemi_disponibilita e chiedi all'utente una \
  NUOVA conferma esplicita prima di richiamare il tool. Solo quando \
  risponde con prenotato=true la prenotazione è stata davvero salvata.

Usa il tool cerca_attivita se l'utente vuole esplorare alternative o avere \
più dettagli su cosa fare in una città, anche senza generare un itinerario \
completo.

Non fare mai calcoli di budget o disponibilità "a mente": usa sempre i tool, \
che lavorano sui dati reali del catalogo.
"""

MAX_TOOL_ITERATIONS = 5  # tetto di sicurezza: evita loop infiniti se l'LLM continua a richiedere tool

WELCOME_MESSAGE = """\
Benvenuto su EasyTrip! Sono il tuo assistente virtuale personale, e sono qua \
per aiutarti a pianificare il viaggio che stai cercando: se vuoi iniziamo \
subito, basta che mi dici solo dove vuoi andare e quando, quanto vuoi che la \
tua vacanza duri, qual è il budget che non vorresti superare, e che tipo di \
vacanza stai cercando.\
"""


def create_welcome_message(conversation: Conversation) -> Message:
    """
    Crea il messaggio di apertura automatico di una nuova conversazione. È
    statico (non generato dall'LLM) perché il suo contenuto non dipende da
    nessun dato utente: evitiamo così una chiamata LLM inutile ad ogni nuova
    chat aperta.
    """
    return Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, content=WELCOME_MESSAGE,
    )


def _build_message_history(conversation: Conversation) -> list[dict]:
    """
    Ricostruisce la history nel formato neutro a partire dai Message salvati
    nel database. I messaggi 'assistant' che in passato hanno generato tool
    call li recuperano da metadata, per mantenere coerente la history anche
    tra richieste HTTP diverse (l'LLM non ha memoria propria tra una chiamata
    e l'altra: la history gliela ricostruiamo sempre da zero noi).
    """
    history = []
    for msg in conversation.messages.order_by('created_at'):
        if msg.role == Message.Role.USER:
            history.append({"role": "user", "content": msg.content})
        elif msg.role == Message.Role.ASSISTANT:
            tool_exchange = msg.metadata.get('tool_exchange') if msg.metadata else None
            if tool_exchange:
                # Questo messaggio assistant in passato ha generato una o più
                # tool call: ricostruiamo l'intera sequenza (assistant -> tool
                # result -> ... ) così il modello mantiene il contesto di cosa
                # è già stato verificato/generato in questa conversazione.
                history.extend(tool_exchange)
            else:
                history.append({"role": "assistant", "content": msg.content})
        # i messaggi 'system' eventuali non vengono ri-accodati: il system
        # prompt è sempre passato a parte a chat_with_tools.
    return history


@transaction.atomic
def handle_user_message(conversation: Conversation, user_text: str) -> Message:
    """
    Punto di ingresso principale: salva il messaggio dell'utente, esegue il
    ciclo di conversazione con l'LLM (con eventuali tool call intermedie), e
    salva/ritorna il messaggio finale dell'assistente.

    Se durante il ciclo il tool genera_itinerario ha prodotto un itinerario
    con successo, lo salviamo nei metadata del messaggio assistente (la
    creazione della Booking effettiva, se l'utente vorrà confermarlo, resta
    un'azione separata lato API/frontend - vedi bookings/views.py).
    """
    Message.objects.create(conversation=conversation, role=Message.Role.USER, content=user_text)

    if not conversation.title:
        conversation.title = user_text[:50]
        conversation.save(update_fields=['title'])

    llm = get_llm_client()
    # Il messaggio utente appena salvato è già incluso da _build_message_history
    # (legge dal DB tutti i messaggi della conversazione, incluso quello creato
    # qui sopra): non va quindi aggiunto di nuovo manualmente.
    messages = _build_message_history(conversation)

    tool_exchange_log = []  # traccia assistant/tool messages generati in questo turno, per la history futura

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = llm.chat_with_tools(
                messages=messages, tools=TOOL_DEFINITIONS, system_prompt=SYSTEM_PROMPT,
            )
        except LLMError as e:
            # Errore del provider (quota/rate-limit esaurita, richiesta
            # rifiutata, timeout, ...): invece di far fallire la richiesta
            # HTTP con un 500, rispondiamo con un messaggio "dell'assistente"
            # che spiega il problema - l'utente può semplicemente riprovare.
            logger.warning(
                "Errore dal provider LLM per la conversation #%d: %s", conversation.id, e,
            )
            return Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=(
                    "Mi dispiace, il servizio di intelligenza artificiale non è al momento "
                    "disponibile (potrebbe aver raggiunto un limite temporaneo di richieste). "
                    "Riprova tra qualche istante."
                ),
                metadata={"tool_exchange": tool_exchange_log, "errore": "llm_provider_error"},
            )

        if not response.has_tool_calls:
            # Il modello ha risposto con testo finale: il turno è concluso.
            # conversation.pending_itinerary riflette sempre lo stato più
            # aggiornato (sia se appena generato, sia dopo eventuali
            # sostituzioni avvenute in questo stesso turno) - lo alleghiamo
            # ai metadata solo se non vuoto, così il frontend può mostrare
            # una scheda itinerario dedicata.
            assistant_message = Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=response.content,
                metadata={
                    "tool_exchange": tool_exchange_log,
                    **({"itinerario_proposto": conversation.pending_itinerary} if conversation.pending_itinerary else {}),
                },
            )
            conversation.save(update_fields=['updated_at'])
            return assistant_message

        # Il modello ha richiesto una o più tool call: le eseguiamo e
        # accodiamo i risultati alla history, poi richiamiamo l'LLM.
        assistant_tool_msg = llm.format_assistant_tool_call_message(response)
        messages.append(assistant_tool_msg)
        tool_exchange_log.append(assistant_tool_msg)

        for tool_call in response.tool_calls:
            logger.info("Tool call richiesta: %s(%s)", tool_call.name, tool_call.arguments)
            result = execute_tool(tool_call.name, tool_call.arguments, conversation=conversation)

            tool_result_msg = llm.format_tool_result_message(tool_call, result)
            messages.append(tool_result_msg)
            tool_exchange_log.append(tool_result_msg)

    # Tetto di iterazioni raggiunto senza una risposta testuale finale:
    # caso anomalo (l'LLM continua a richiedere tool), rispondiamo con un
    # messaggio di cortesia invece di restituire un errore tecnico.
    logger.warning(
        "Raggiunto il limite di %d iterazioni di tool-calling per la conversation #%d senza risposta finale.",
        MAX_TOOL_ITERATIONS, conversation.id,
    )
    fallback_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=(
            "Mi scuso, sto avendo difficoltà a completare questa richiesta. "
            "Potresti riformulare cosa stai cercando (budget, nazione, mese e "
            "preferenze di viaggio)?"
        ),
        metadata={"tool_exchange": tool_exchange_log, "errore": "max_tool_iterations_reached"},
    )
    return fallback_message
