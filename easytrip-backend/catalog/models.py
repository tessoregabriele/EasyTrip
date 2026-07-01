from django.db import models
from django.core.validators import MinValueValidator
from pgvector.django import VectorField


class Country(models.Model):
    """Nazione di interesse per il viaggio."""
    name = models.CharField(max_length=100, unique=True)
    iso_code = models.CharField(max_length=2, unique=True, help_text="Codice ISO 3166-1 alpha-2, es. 'IT'")

    class Meta:
        verbose_name_plural = "countries"
        ordering = ['name']

    def __str__(self):
        return self.name


class City(models.Model):
    """Città all'interno di una nazione, usata per localizzare hotel/attività/aeroporti."""
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='cities')
    name = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name_plural = "cities"
        unique_together = ['country', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.name}, {self.country.name}"


class Airport(models.Model):
    """Aeroporto, usato come punto di partenza/arrivo per i voli."""
    iata_code = models.CharField(max_length=3, unique=True, help_text="Codice IATA, es. 'MXP'")
    name = models.CharField(max_length=150)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='airports')

    def __str__(self):
        return f"{self.iata_code} - {self.name}"


class ActivityCategory(models.Model):
    """
    Categoria di attività (cultura, sport, relax, nightlife, ecc.).
    Tabella separata invece di scelte fisse per poter aggiungere categorie
    senza migrazioni e per poterle riusare come filtro nelle preferenze utente.
    """
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        verbose_name_plural = "activity categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Hotel(models.Model):
    """Albergo. Le date di disponibilità e il costo sono gestiti tramite HotelAvailability."""
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='hotels')
    address = models.CharField(max_length=255, blank=True)
    stars = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    # Per il RAG: embedding della descrizione + target ideale (es. "famiglie, coppie")
    description_embedding = VectorField(dimensions=384, null=True, blank=True)
    target_audience = models.CharField(
        max_length=255, blank=True,
        help_text="Target ideale, es. 'famiglie, giovani coppie'"
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class HotelAvailability(models.Model):
    """
    Disponibilità e costo per notte di un hotel in una data specifica.
    Una riga per ogni (hotel, data) disponibile, con costo per quella notte
    e numero di camere libere — permette di gestire variazioni di prezzo
    stagionali e overbooking in modo naturale.
    """
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='availabilities')
    date = models.DateField()
    price_per_night = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    rooms_available = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ['hotel', 'date']
        ordering = ['date']

    def __str__(self):
        return f"{self.hotel.name} - {self.date} (€{self.price_per_night})"


class Activity(models.Model):
    """Attività turistica (museo, tour, esperienza sportiva, ecc.)."""
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='activities')
    category = models.ForeignKey(ActivityCategory, on_delete=models.PROTECT, related_name='activities')
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    base_price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])

    # Per il RAG: embedding della descrizione testuale + target ideale
    description_embedding = VectorField(dimensions=384, null=True, blank=True)
    target_audience = models.CharField(
        max_length=255, blank=True,
        help_text="Target ideale, es. 'famiglie, sportivi, giovani'"
    )

    class Meta:
        verbose_name_plural = "activities"
        ordering = ['name']

    def __str__(self):
        return self.name


class ActivityAvailability(models.Model):
    """Data specifica in cui un'attività è disponibile/prenotabile, con eventuale variazione di prezzo e posti."""
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='availabilities')
    date = models.DateField()
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    spots_available = models.PositiveIntegerField(default=10)

    class Meta:
        unique_together = ['activity', 'date']
        ordering = ['date']

    def __str__(self):
        return f"{self.activity.name} - {self.date}"


class Flight(models.Model):
    """
    Volo singolo (una direzione). Un itinerario andata/ritorno è composto
    da due Flight collegati nella prenotazione (outbound + return).
    """
    flight_number = models.CharField(max_length=20)
    departure_airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='departures')
    arrival_airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='arrivals')
    departure_datetime = models.DateTimeField()
    arrival_datetime = models.DateTimeField()
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    seats_available = models.PositiveIntegerField(default=50)

    class Meta:
        ordering = ['departure_datetime']

    def __str__(self):
        return f"{self.flight_number}: {self.departure_airport.iata_code} -> {self.arrival_airport.iata_code} ({self.departure_datetime.date()})"
