"""
Ricerca semantica (RAG) su Hotel e Activity usando similarità vettoriale
con pgvector. Usata per affinare i risultati del motore di generazione
itinerario sulla base di preferenze testuali libere dell'utente
(es. "qualcosa di rilassante per famiglie con bambini piccoli"), in aggiunta
al filtro rigido per categoria/città/data già disponibile nelle query Django.
"""
from pgvector.django import CosineDistance

from catalog.models import Activity, Hotel
from .embeddings import generate_embedding


def search_activities_semantic(query_text: str, queryset=None, top_k: int = 10):
    """
    Ordina le attività per similarità semantica rispetto a query_text.
    Se queryset è fornito, la ricerca semantica viene applicata SOPRA i
    filtri già presenti nel queryset (es. città, categoria, data disponibile),
    così il RAG affina invece di sostituire i vincoli rigidi.
    """
    base_qs = queryset if queryset is not None else Activity.objects.all()
    query_embedding = generate_embedding(query_text)

    return (
        base_qs
        .filter(description_embedding__isnull=False)
        .annotate(distance=CosineDistance('description_embedding', query_embedding))
        .order_by('distance')[:top_k]
    )


def search_hotels_semantic(query_text: str, queryset=None, top_k: int = 10):
    """Equivalente di search_activities_semantic, per gli hotel."""
    base_qs = queryset if queryset is not None else Hotel.objects.all()
    query_embedding = generate_embedding(query_text)

    return (
        base_qs
        .filter(description_embedding__isnull=False)
        .annotate(distance=CosineDistance('description_embedding', query_embedding))
        .order_by('distance')[:top_k]
    )
