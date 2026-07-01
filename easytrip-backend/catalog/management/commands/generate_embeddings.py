from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Hotel, Activity
from catalog.rag.embeddings import generate_embeddings_batch


class Command(BaseCommand):
    help = (
        "Genera (o rigenera) gli embedding per le descrizioni di Hotel e "
        "Activity, necessari per la ricerca semantica RAG. "
        "Scarica il modello di embedding al primo utilizzo (~440MB, richiede "
        "connessione internet una tantum)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--only', choices=['hotels', 'activities'], default=None,
            help="Limita la generazione a un solo tipo di entità."
        )

    def handle(self, *args, **options):
        only = options.get('only')

        if only != 'activities':
            self._embed_hotels()
        if only != 'hotels':
            self._embed_activities()

    @transaction.atomic
    def _embed_hotels(self):
        hotels = list(Hotel.objects.all())
        if not hotels:
            self.stdout.write("Nessun hotel da elaborare.")
            return

        self.stdout.write(f"Genero embedding per {len(hotels)} hotel...")
        texts = [
            f"{h.name}. {h.description} Target ideale: {h.target_audience}."
            for h in hotels
        ]
        embeddings = generate_embeddings_batch(texts)

        for hotel, embedding in zip(hotels, embeddings):
            hotel.description_embedding = embedding
        Hotel.objects.bulk_update(hotels, ['description_embedding'])
        self.stdout.write(self.style.SUCCESS(f"Embedding generati per {len(hotels)} hotel."))

    @transaction.atomic
    def _embed_activities(self):
        activities = list(Activity.objects.all())
        if not activities:
            self.stdout.write("Nessuna attività da elaborare.")
            return

        self.stdout.write(f"Genero embedding per {len(activities)} attività...")
        texts = [
            f"{a.name}. {a.description} Categoria: {a.category.name}. Target ideale: {a.target_audience}."
            for a in activities
        ]
        embeddings = generate_embeddings_batch(texts)

        for activity, embedding in zip(activities, embeddings):
            activity.description_embedding = embedding
        Activity.objects.bulk_update(activities, ['description_embedding'])
        self.stdout.write(self.style.SUCCESS(f"Embedding generati per {len(activities)} attività."))
