-- Eseguito automaticamente da Postgres alla prima creazione del volume dati.
-- Attiva l'estensione pgvector, necessaria per i campi VectorField usati
-- dal RAG su Hotel e Activity (vedi catalog/models.py).
CREATE EXTENSION IF NOT EXISTS vector;
