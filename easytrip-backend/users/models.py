from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Utente custom. Estende AbstractUser di Django per poter aggiungere
    campi specifici al dominio travel (es. preferenze di default) senza
    dover migrare in futuro da un modello User non estendibile.
    """
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=30, blank=True)

    # Preferenze di default dell'utente, utili per pre-compilare future
    # richieste di itinerario (facoltative, modificabili in ogni richiesta)
    default_budget = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    preferred_activities = models.JSONField(
        default=list, blank=True,
        help_text="Lista di categorie preferite, es. ['cultura', 'relax']"
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return self.username
