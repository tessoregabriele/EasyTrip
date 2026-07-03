# EasyTrip

Un assistente virtuale conversazionale per la pianificazione di viaggi.
L'utente chatta con un assistente AI descrivendo budget, destinazione,
periodo e preferenze; l'assistente genera un itinerario completo (volo,
hotel, attività giorno per giorno) rispettando vincoli reali di
disponibilità e budget, permette di rivedere e sostituire singoli
componenti non graditi, e infine salva la prenotazione confermata.

## Come funziona

L'LLM (Groq o Gemini, intercambiabili) **non genera mai direttamente**
l'itinerario né fa calcoli di budget: conduce solo la conversazione con
l'utente e invoca funzioni Python deterministiche (ricerca nel catalogo,
motore di generazione dell'itinerario, salvataggio della prenotazione)
tramite tool-calling. In questo modo i vincoli numerici — budget,
disponibilità reale di voli/hotel/attività — sono sempre rispettati
esattamente, indipendentemente da eventuali imprecisioni del modello
linguistico.

La ricerca di hotel e attività più adatti alle preferenze dell'utente
usa un livello di ricerca semantica (RAG) basato su embedding testuali
e pgvector.

## Stack tecnico

- **Backend**: Django + Django REST Framework, PostgreSQL + pgvector
  (containerizzato via Docker), autenticazione JWT
- **Frontend**: React + Vite (JavaScript), single-page application
- **LLM**: Groq o Gemini (a scelta, Groq di default), integrati tramite tool-calling
- **RAG**: embedding multilingua (`paraphrase-multilingual-MiniLM-L12-v2`)
  per la ricerca semantica su hotel e attività

## Struttura del progetto

- [`easytrip-backend/`](easytrip-backend/) — API Django: catalogo viaggi,
  motore di generazione itinerari, chat/LLM, utenti e prenotazioni
- [`easytrip-frontend/`](easytrip-frontend/) — interfaccia utente React

## Requisiti

- Python 3.11+
- Node.js 18+ e npm
- Docker (per il database PostgreSQL + pgvector)
- Una API key gratuita per un provider LLM: [Groq](https://console.groq.com)
  o [Gemini](https://aistudio.google.com)

## Come avviare il progetto

### Primo avvio (Windows)

Su Windows, `first_start.bat` automatizza tutto il setup iniziale: avvia il
database Docker, crea il virtualenv e installa le dipendenze backend,
genera il file `.env` del backend con una `SECRET_KEY` casuale, esegue le
migrazioni, crea il superuser, popola i dati di esempio, genera gli
embedding per il RAG, e installa le dipendenze frontend.

```bash
first_start.bat
```

Va lanciato una sola volta, dopo il clone della repo. Al termine ricorda
di inserire una API key valida (Groq o Gemini) in `easytrip-backend\.env`
prima di avviare il progetto.

Dopo il primo avvio, per le esecuzioni successive bastano
`start_all.bat` (avvia database, backend e frontend) e `stop_all.bat`
(ferma tutto).

### Setup manuale (macOS/Linux o passo per passo)

#### 1. Database

```bash
cd easytrip-backend
docker compose up -d
```

#### 2. Backend

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

cp .env.example .env
# Apri .env e imposta SECRET_KEY e una API key LLM (GROQ_API_KEY o GEMINI_API_KEY)

python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data
python manage.py generate_embeddings

python manage.py runserver
```

Backend disponibile su `http://localhost:8000`.

#### 3. Frontend

In un secondo terminale:

```bash
cd easytrip-frontend
cp .env.example .env
npm install
npm run dev
```

Frontend disponibile su `http://localhost:3000`.

