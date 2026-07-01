"""
Generazione di embedding testuali per il RAG, usando fastembed (ONNX Runtime,
esecuzione locale su CPU, nessuna chiamata API esterna né costi).

Il modello viene scaricato automaticamente da Hugging Face al primo utilizzo
(circa 440MB) e poi mantenuto in cache locale (~/.cache/fastembed o simile),
quindi richiede una connessione internet attiva solo la prima volta.
"""
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Carica il modello di embedding una sola volta per processo (è costoso
    da istanziare). lru_cache garantisce che le chiamate successive
    riutilizzino la stessa istanza.
    """
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=settings.EMBEDDING_MODEL_NAME)


def generate_embedding(text: str) -> list[float]:
    """Genera l'embedding per un singolo testo. Ritorna una lista di float (compatibile con pgvector)."""
    model = get_embedding_model()
    embedding = list(model.embed([text]))[0]
    return embedding.tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Genera embedding per più testi in batch (più efficiente di chiamate singole)."""
    model = get_embedding_model()
    return [e.tolist() for e in model.embed(texts)]
