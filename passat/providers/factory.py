"""Tworzy wybranego dostawcę na podstawie ustawień aplikacji."""

from dataclasses import dataclass

from passat.providers.base import BaseAIProvider, ProviderConfigurationError
from passat.providers.groq import GroqProvider
from passat.providers.offline import OfflineProvider
from passat.settings import Settings


@dataclass(frozen=True)
class ProviderSelection:
    provider: BaseAIProvider
    provider_name: str
    is_offline: bool
    notice: str | None = None


def create_provider(settings: Settings) -> ProviderSelection:
    if settings.provider == "offline":
        provider = OfflineProvider()
        return ProviderSelection(provider, provider.name, True)

    if settings.provider not in ("gemini", "groq"):
        raise ProviderConfigurationError(
            f"Nieobsługiwany dostawca: {settings.provider}. Dostępne teraz: groq, gemini, offline."
        )

    if settings.provider == "groq":
        if not settings.groq_api_key:
            provider = OfflineProvider()
            return ProviderSelection(
                provider,
                provider.name,
                True,
                "Brak GROQ_API_KEY. Dodaj klucz GroqCloud do pliku .env; Passat działa offline.",
            )
        provider = GroqProvider(settings.groq_api_key, settings.groq_model)
        return ProviderSelection(provider, provider.name, False)

    if not settings.gemini_api_key:
        provider = OfflineProvider()
        return ProviderSelection(
            provider,
            provider.name,
            True,
            "Brak GEMINI_API_KEY. Passat działa w trybie awaryjnym offline.",
        )

    # Gemini pozostaje opcjonalne i nie jest importowane przy uruchamianiu Groq.
    from passat.providers.gemini import GeminiProvider

    provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    return ProviderSelection(provider, provider.name, False)
