import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import (
    Country, City, Airport, ActivityCategory,
    Hotel, HotelAvailability, Activity, ActivityAvailability, Flight,
)


class Command(BaseCommand):
    help = "Popola il database con dati di esempio (paesi, città, hotel, attività, voli)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help="Svuota i dati del catalogo prima di rigenerarli."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write("Svuoto i dati esistenti del catalogo...")
            ActivityAvailability.objects.all().delete()
            HotelAvailability.objects.all().delete()
            Flight.objects.all().delete()
            Activity.objects.all().delete()
            Hotel.objects.all().delete()
            Airport.objects.all().delete()
            City.objects.all().delete()
            Country.objects.all().delete()
            ActivityCategory.objects.all().delete()

        self.stdout.write("Creo categorie di attività...")
        categories = {}
        for name, slug in [
            ('Cultura', 'cultura'), ('Sport', 'sport'), ('Relax', 'relax'),
            ('Nightlife', 'nightlife'), ('Natura', 'natura'), ('Cibo e Vino', 'cibo-vino'),
        ]:
            cat, _ = ActivityCategory.objects.get_or_create(name=name, slug=slug)
            categories[slug] = cat

        self.stdout.write("Creo nazioni, città e aeroporti...")

        italy, _ = Country.objects.get_or_create(name='Italia', iso_code='IT')
        spain, _ = Country.objects.get_or_create(name='Spagna', iso_code='ES')
        france, _ = Country.objects.get_or_create(name='Francia', iso_code='FR')

        rome, _ = City.objects.get_or_create(country=italy, name='Roma', defaults={'latitude': 41.9028, 'longitude': 12.4964})
        florence, _ = City.objects.get_or_create(country=italy, name='Firenze', defaults={'latitude': 43.7696, 'longitude': 11.2558})
        barcelona, _ = City.objects.get_or_create(country=spain, name='Barcellona', defaults={'latitude': 41.3851, 'longitude': 2.1734})
        paris, _ = City.objects.get_or_create(country=france, name='Parigi', defaults={'latitude': 48.8566, 'longitude': 2.3522})
        milan, _ = City.objects.get_or_create(country=italy, name='Milano', defaults={'latitude': 45.4642, 'longitude': 9.1900})

        airports_data = [
            ('FCO', 'Roma Fiumicino', rome),
            ('FLR', 'Firenze Peretola', florence),
            ('BCN', 'Barcellona El Prat', barcelona),
            ('CDG', 'Parigi Charles de Gaulle', paris),
            ('MXP', 'Milano Malpensa', milan),
        ]
        airports = {}
        for code, name, city in airports_data:
            airport, _ = Airport.objects.get_or_create(
                iata_code=code, defaults={'name': name, 'city': city}
            )
            airports[code] = airport

        self.stdout.write("Creo hotel con disponibilità...")

        hotels_data = [
            ('Hotel Colosseo Charme', rome, 4, 70, "famiglie, coppie"),
            ('Roma Backpackers Hostel', rome, 2, 35, "giovani, studenti"),
            ('Firenze Boutique Hotel', florence, 4, 80, "coppie, amanti dell'arte"),
            ('Barcelona Beach Resort', barcelona, 4, 90, "famiglie, giovani"),
            ('Paris Charme Hotel', paris, 5, 150, "coppie, viaggiatori di lusso"),
            ('Milano Business Inn', milan, 3, 60, "viaggiatori business, coppie"),
        ]
        hotels = []
        for name, city, stars, base_price, target in hotels_data:
            hotel, _ = Hotel.objects.get_or_create(
                name=name, city=city,
                defaults={
                    'stars': stars,
                    'description': f"{name} è una struttura {stars} stelle situata nel cuore di {city.name}, ideale per {target}.",
                    'target_audience': target,
                }
            )
            hotels.append((hotel, base_price))

        # Disponibilità per i prossimi 9 mesi, con piccola variazione di prezzo
        today = date.today()
        for hotel, base_price in hotels:
            for day_offset in range(0, 270):
                d = today + timedelta(days=day_offset)
                variation = random.uniform(0.85, 1.25)
                price = Decimal(str(round(base_price * variation, 2)))
                HotelAvailability.objects.get_or_create(
                    hotel=hotel, date=d,
                    defaults={'price_per_night': price, 'rooms_available': random.randint(1, 10)}
                )

        self.stdout.write("Creo attività con disponibilità...")

        activities_data = [
            ('Tour guidato del Colosseo', rome, 'cultura', 45, "famiglie, amanti della storia"),
            ('Corso di cucina romana', rome, 'cibo-vino', 65, "coppie, amanti del cibo"),
            ('Aperitivo in terrazza panoramica', rome, 'nightlife', 30, "giovani, coppie"),
            ('Visita guidata Galleria degli Uffizi', florence, 'cultura', 40, "amanti dell'arte, famiglie"),
            ('Degustazione vini in Chianti', florence, 'cibo-vino', 75, "coppie, amanti del vino"),
            ('Spa e relax in centro storico', florence, 'relax', 90, "coppie"),
            ('Tour delle Ramblas e Sagrada Familia', barcelona, 'cultura', 35, "famiglie, turisti"),
            ('Lezione di surf a Barceloneta', barcelona, 'sport', 55, "giovani, sportivi"),
            ('Discoteca e vita notturna Barcellona', barcelona, 'nightlife', 25, "giovani"),
            ('Crociera sulla Senna', paris, 'relax', 35, "coppie, famiglie"),
            ('Tour della Torre Eiffel e Louvre', paris, 'cultura', 50, "famiglie, amanti dell'arte"),
            ('Passeggiata nei Navigli e aperitivo', milan, 'nightlife', 20, "giovani, coppie"),
        ]
        for name, city, cat_slug, base_price, target in activities_data:
            activity, _ = Activity.objects.get_or_create(
                name=name, city=city,
                defaults={
                    'category': categories[cat_slug],
                    'description': f"{name}: un'esperienza pensata per {target}.",
                    'duration_minutes': random.choice([60, 90, 120, 180]),
                    'base_price': Decimal(str(base_price)),
                    'target_audience': target,
                }
            )
            for day_offset in range(0, 270):
                d = today + timedelta(days=day_offset)
                ActivityAvailability.objects.get_or_create(
                    activity=activity, date=d,
                    defaults={'price': activity.base_price, 'spots_available': random.randint(5, 30)}
                )

        self.stdout.write("Creo voli...")

        routes = [
            ('MXP', 'FCO'), ('MXP', 'BCN'), ('MXP', 'CDG'), ('MXP', 'FLR'),
        ]
        flight_counter = 100
        for dep_code, arr_code in routes:
            dep_airport = airports[dep_code]
            arr_airport = airports[arr_code]
            for day_offset in range(0, 270, 2):  # un volo ogni 2 giorni circa
                d = today + timedelta(days=day_offset)
                flight_counter += 1
                # Volo di andata
                Flight.objects.get_or_create(
                    flight_number=f"TV{flight_counter}",
                    departure_airport=dep_airport,
                    arrival_airport=arr_airport,
                    departure_datetime=d.strftime('%Y-%m-%d') + 'T08:00:00+02:00',
                    defaults={
                        'arrival_datetime': d.strftime('%Y-%m-%d') + 'T10:00:00+02:00',
                        'price': Decimal(str(random.randint(60, 250))),
                        'seats_available': random.randint(20, 180),
                    }
                )
                # Volo di ritorno
                Flight.objects.get_or_create(
                    flight_number=f"TV{flight_counter}R",
                    departure_airport=arr_airport,
                    arrival_airport=dep_airport,
                    departure_datetime=d.strftime('%Y-%m-%d') + 'T18:00:00+02:00',
                    defaults={
                        'arrival_datetime': d.strftime('%Y-%m-%d') + 'T20:00:00+02:00',
                        'price': Decimal(str(random.randint(60, 250))),
                        'seats_available': random.randint(20, 180),
                    }
                )

        self.stdout.write(self.style.SUCCESS(
            f"Seed completato: {Country.objects.count()} nazioni, {City.objects.count()} città, "
            f"{Hotel.objects.count()} hotel, {Activity.objects.count()} attività, "
            f"{Flight.objects.count()} voli."
        ))
