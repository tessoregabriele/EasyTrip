# Challenge: Assistente Virtuale per Viaggi Personalizzati

## Obiettivo

Sviluppare un assistente virtuale conversazionale per il settore travel & experiences, in grado di comprendere le esigenze dell’utente e generare itinerari personalizzati completi, fino alla prenotazione.

 

## Input Utente

L’assistente deve raccogliere e gestire i seguenti dati:

- Budget totale
- Nazione di interesse
- Preferenze sulle attività (es. cultura, sport, relax, nightlife, ecc.)
- Periodo di viaggio (espresso come mese)

## Funzionalità principali

Il sistema deve essere in grado di:

- **Conversazione intelligente**:
  - Interazione via chat in linguaggio naturale
  - Comprensione del contesto e delle richieste utente
- **Raccolta requisiti**: Estrazione e validazione dei dati utente (budget, destinazione, attività, periodo)
- **Generazione itinerario**: Creazione di un itinerario completo che includa:
    - Volo di andata e ritorno
    - Albergo per ogni notte
    - Attività per ogni giorno
    - **Rispetto dei vincoli**: Budget, Disponibilità, Preferenze utente
- **Prenotazione**: Possibilità di prenotare l’intero itinerario tramite chat, e salvataggio dello stato delle prenotazioni
 

## Architettura del sistema

1. ### Database

**Database principale** (Relazionale o NoSQL)

Deve contenere almeno le seguenti entità/tabelle:
- Utenti
- Alberghi (date disponibili e costo per notte)
- Attività (date disponibili)
- Voli (aeroporto di partenza e arrivo, date, costo)
- Prenotazioni (utente, itinerario)
 
**Database vettoriale**

Utilizzato per supportare un approccio RAG.

Contenuti:
- Descrizioni testuali delle attività
- Informazioni sui target ideali (es. famiglie, giovani, sportivi)
 
2. ### Backend

Tecnologie suggerite: a scelta (Node.js, Django, Flask, Ruby on Rails)
Responsabilità:
- Esposizione di API REST
- Implementazione delle logiche di business:


3. **Frontend**

Tecnologie: a scelta (es HTML, CSS, JavaScript oppure framework React, Vue, Angular)

Funzionalità richieste:
- Registrazione e autenticazione utente
- Interfaccia chat con assistente
- Visualizzazione degli itinerari proposti
- Prenotazione tramite chat
- Dashboard con visualizzazione delle prenotazioni effettuate
 

Funzionalità opzionali:
- Upload di immagini da parte dell’utente per indicare preferenze su attività o strutture
- Modifica di itinerari già prenotati (con verifica disponibilità)
- Storico delle conversazioni utente
- Altre funzionalità a discrezione dello sviluppatore, potenzialmente rilevanti per lo use case
 

## Deliverable

Repository Git (GitHub o GitLab) opzionale e successiva condivisione con il reviewer del link.

La repo deve contenere:
- Codice sorgente
- Istruzioni per l’esecuzione (README)
- Eventuali note architetturali