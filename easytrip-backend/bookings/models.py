from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Booking(models.Model):
    """
    Prenotazione di un itinerario completo per un utente.
    Funziona da "contenitore": il volo andata/ritorno, gli hotel per notte
    e le attività per giorno sono collegati tramite le tabelle correlate
    qui sotto (BookingFlight, BookingHotelStay, BookingActivity).
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Bozza'           # itinerario generato ma non confermato
        CONFIRMED = 'confirmed', 'Confermata'
        CANCELLED = 'cancelled', 'Annullata'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Dati della richiesta originale dell'utente, salvati per riferimento
    # (utili anche in futuro per il motore di generazione/RAG)
    country = models.ForeignKey('catalog.Country', on_delete=models.PROTECT, related_name='bookings')
    total_budget = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    requested_activity_preferences = models.JSONField(
        default=list, blank=True,
        help_text="Categorie richieste dall'utente al momento della generazione, es. ['cultura', 'relax']"
    )
    travel_month = models.PositiveSmallIntegerField(
        help_text="Mese di viaggio richiesto (1-12), salvato per riferimento storico"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Booking #{self.id} - {self.user.username} ({self.get_status_display()})"

    @property
    def total_cost(self):
        """Costo totale calcolato dinamicamente dai componenti dell'itinerario."""
        flights_total = sum(bf.price for bf in self.flights.all())
        hotel_total = sum(bh.price_per_night for bh in self.hotel_stays.all())
        activities_total = sum(ba.price for ba in self.activities.all())
        return flights_total + hotel_total + activities_total


class BookingFlight(models.Model):
    """Volo (andata o ritorno) incluso in una prenotazione."""

    class Direction(models.TextChoices):
        OUTBOUND = 'outbound', 'Andata'
        RETURN = 'return', 'Ritorno'

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='flights')
    flight = models.ForeignKey('catalog.Flight', on_delete=models.PROTECT, related_name='booking_flights')
    direction = models.CharField(max_length=10, choices=Direction.choices)

    # Prezzo "congelato" al momento della prenotazione: il prezzo del volo
    # in catalog potrebbe cambiare dopo, ma la prenotazione deve restare coerente
    # con quanto pagato dall'utente.
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = ['booking', 'direction']

    def __str__(self):
        return f"{self.booking_id} - {self.get_direction_display()}: {self.flight.flight_number}"


class BookingHotelStay(models.Model):
    """Singola notte di soggiorno in un hotel all'interno di una prenotazione."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='hotel_stays')
    hotel = models.ForeignKey('catalog.Hotel', on_delete=models.PROTECT, related_name='booking_stays')
    date = models.DateField(help_text="Notte di soggiorno (data di check-in per quella notte)")
    price_per_night = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = ['booking', 'date']  # una sola camera/hotel per notte nello stesso itinerario
        ordering = ['date']

    def __str__(self):
        return f"{self.booking_id} - {self.hotel.name} ({self.date})"


class BookingActivity(models.Model):
    """Attività prevista in un giorno specifico dell'itinerario prenotato."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='activities')
    activity = models.ForeignKey('catalog.Activity', on_delete=models.PROTECT, related_name='booking_activities')
    date = models.DateField()
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.booking_id} - {self.activity.name} ({self.date})"
