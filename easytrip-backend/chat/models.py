from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """
    Una conversazione tra l'utente e l'assistente. Raggruppa i messaggi
    per supportare lo storico delle conversazioni (funzionalità opzionale)
    e, in futuro, il contesto da passare all'LLM.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, blank=True, help_text="Titolo generato automaticamente o dal primo messaggio")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Collegamento opzionale alla prenotazione generata/discussa in questa conversazione
    booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations'
    )

    # Stato dell'itinerario attualmente in fase di revisione con l'utente
    # (non ancora confermato/salvato come Booking). Struttura:
    #   {
    #     "country_id": int, "total_budget": "...", "travel_month": int,
    #     "outbound_flight": {...}, "return_flight": {...},
    #     "hotel_stays": [{... , "approvato": bool}, ...],
    #     "daily_activities": [{..., "approvato": bool}, ...],
    #   }
    # Viene popolato quando genera_itinerario ha successo, aggiornato dai
    # tool di sostituzione, e azzerato (tornato a {}) quando l'itinerario
    # viene confermato e salvato come Booking. Vedi chat/llm/tools.py.
    pending_itinerary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation #{self.id} - {self.user.username}"


class Message(models.Model):
    """Singolo messaggio in una conversazione."""

    class Role(models.TextChoices):
        USER = 'user', 'Utente'
        ASSISTANT = 'assistant', 'Assistente'
        SYSTEM = 'system', 'Sistema'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()

    # Spazio per metadati strutturati (es. itinerario proposto, dati estratti)
    # che il livello LLM/RAG popolerà nelle fasi successive.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:50]}"
