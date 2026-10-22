"""Integracja z GroqCloud przez oficjalny pakiet Python groq."""

import time
from collections.abc import Sequence

import groq
from groq import Groq

from passat.models import ChatMessage
from passat.providers.base import (
    BaseAIProvider,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


class GroqProvider(BaseAIProvider):
    name = "GroqCloud"
    MAX_RATE_LIMIT_WAIT_SECONDS = 15

    def __init__(self, api_key: str, model: str, client=None):
        if not api_key.strip():
            raise ProviderAuthenticationError("Brakuje klucza GROQ_API_KEY.")
        self.model = model
        # Zero automatycznych retry w SDK. Ograniczone ponowienie 429 obsługujemy
        # jawnie, aby respektować Retry-After i nie wysyłać duplikatów w tle.
        self.client = client or Groq(
            api_key=api_key,
            timeout=60.0,
            max_retries=0,
        )

    def generate_reply(
        self,
        message: str,
        history: Sequence[ChatMessage],
        system_instruction: str,
    ) -> str:
        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(
            {
                "role": "assistant" if item.role == "assistant" else "user",
                "content": item.content,
            }
            for item in history
        )
        messages.append({"role": "user", "content": message})

        for attempt in range(2):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=1024,
                    reasoning_effort="none",
                    timeout=60.0,
                )
            except groq.RateLimitError as error:
                retry_after = self._retry_after_seconds(error)
                if (
                    attempt == 0
                    and retry_after is not None
                    and 0 <= retry_after <= self.MAX_RATE_LIMIT_WAIT_SECONDS
                ):
                    time.sleep(retry_after)
                    continue
                if retry_after is not None:
                    message = (
                        f"Limit GroqCloud (HTTP 429). Odczekaj co najmniej "
                        f"{retry_after:g} s przed kolejną próbą."
                    )
                else:
                    message = "Osiągnięto limit GroqCloud (HTTP 429). Spróbuj później."
                raise ProviderRateLimitError(message) from None
            except groq.AuthenticationError:
                raise ProviderAuthenticationError(
                    "Klucz GROQ_API_KEY jest nieprawidłowy lub został odrzucony."
                ) from None
            except groq.PermissionDeniedError:
                raise ProviderAuthenticationError(
                    "Klucz GroqCloud nie ma dostępu do wybranego modelu."
                ) from None
            except groq.NotFoundError:
                raise ProviderUnavailableError(
                    f"Model {self.model} nie jest dostępny dla tego klucza GroqCloud."
                ) from None
            except groq.APIConnectionError:
                raise ProviderUnavailableError(
                    "Nie udało się połączyć z GroqCloud albo upłynął limit czasu. "
                    "Sprawdź internet i spróbuj ponownie."
                ) from None
            except groq.APIStatusError as error:
                if error.status_code >= 500:
                    detail = "Błąd serwera GroqCloud"
                else:
                    detail = "GroqCloud odrzuciło żądanie"
                raise ProviderUnavailableError(
                    f"{detail} (HTTP {error.status_code}). Spróbuj ponownie później."
                ) from None
            except groq.APIError:
                raise ProviderUnavailableError(
                    "GroqCloud zwróciło nieoczekiwaną odpowiedź."
                ) from None

            try:
                reply = completion.choices[0].message.content
            except (AttributeError, IndexError, TypeError):
                reply = None
            if not reply or not reply.strip():
                raise ProviderUnavailableError("GroqCloud nie zwróciło tekstu odpowiedzi.")
            return reply.strip()

        raise ProviderRateLimitError("Osiągnięto limit żądań GroqCloud. Spróbuj później.")

    @staticmethod
    def _retry_after_seconds(error: groq.RateLimitError) -> float | None:
        """Czyta serwerowy czas oczekiwania, jeśli odpowiedź go zawiera."""
        value = error.response.headers.get("retry-after")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
