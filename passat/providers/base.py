"""Wspólny kontrakt dostawcy odpowiedzi AI."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from passat.models import ChatMessage


class AIProviderError(Exception):
    """Bezpieczny dla interfejsu błąd dostawcy (bez surowej treści z API)."""


class ProviderAuthenticationError(AIProviderError):
    """Klucz lub uprawnienia dostawcy są nieprawidłowe."""


class ProviderRateLimitError(AIProviderError):
    """Dostawca odrzucił żądanie z powodu limitu."""


class ProviderUnavailableError(AIProviderError):
    """Dostawca nie odpowiedział albo zwrócił nieoczekiwany wynik."""


class ProviderConfigurationError(AIProviderError):
    """Ustawienie dostawcy jest nieobsługiwane."""


class BaseAIProvider(ABC):
    """Dostawca przyjmuje historię Passata, nie format konkretnego API."""

    name = "AI"

    @abstractmethod
    def generate_reply(
        self,
        message: str,
        history: Sequence[ChatMessage],
        system_instruction: str,
    ) -> str:
        """Zwraca tekst odpowiedzi na wiadomość użytkownika."""
