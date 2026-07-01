"""
Factory per ottenere il client LLM configurato, in base alla variabile
d'ambiente LLM_PROVIDER ('groq' o 'gemini'). Punto unico da cui il resto
dell'applicazione ottiene un'istanza di LLMClient, senza sapere quale
provider concreto sta usando sotto.
"""
from django.conf import settings

from .base import LLMClient
from .groq_client import GroqClient
from .gemini_client import GeminiClient


def get_llm_client() -> LLMClient:
    provider = settings.LLM_PROVIDER.lower()

    if provider == "groq":
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER='groq' ma GROQ_API_KEY non è impostata nel .env"
            )
        return GroqClient(api_key=settings.GROQ_API_KEY)

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER='gemini' ma GEMINI_API_KEY non è impostata nel .env"
            )
        return GeminiClient(api_key=settings.GEMINI_API_KEY)

    raise RuntimeError(
        f"LLM_PROVIDER='{provider}' non valido. Valori supportati: 'groq', 'gemini'."
    )
