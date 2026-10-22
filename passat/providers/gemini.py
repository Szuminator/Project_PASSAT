"""Integracja z Gemini przez oficjalny pakiet Google Gen AI SDK."""

from collections.abc import Sequence

import httpx
from google import genai
from google.genai import errors, types

from passat.models import ChatMessage
from passat.providers.base import (
    BaseAIProvider,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


class GeminiProvider(BaseAIProvider):
    name = "Gemini"

    def __init__(self, api_key: str, model: str, client=None):
        if not api_key.strip():
            raise ProviderAuthenticationError("Brakuje klucza GEMINI_API_KEY.")
        self.model = model
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                # 504 to przekroczenie czasu po stronie serwera. Dajemy modelowi
                # więcej czasu; wywołanie i tak działa poza wątkiem GUI.
                timeout=120_000,
                # 503 bywa chwilowy. Robimy najwyżej jedno ponowienie z
                # domyślnym krótkim backoffem SDK, wyłącznie dla tego błędu.
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    http_status_codes=[503],
                ),
            ),
        )

    def generate_reply(
        self,
        message: str,
        history: Sequence[ChatMessage],
        system_instruction: str,
    ) -> str:
        contents = [
            types.Content(
                role="user" if item.role == "user" else "model",
                parts=[types.Part.from_text(text=item.content)],
            )
            for item in history
        ]
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=512,
                    # Dla zwykłej rozmowy niski poziom ogranicza zbędne
                    # rozumowanie i zwykle przyspiesza odpowiedź.
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            )
            reply = response.text
        except errors.APIError as error:
            if error.code in (401, 403):
                raise ProviderAuthenticationError(
                    "Klucz Gemini jest nieprawidłowy lub nie ma dostępu do tego modelu."
                ) from None
            if error.code == 429:
                raise ProviderRateLimitError(
                    "Osiągnięto limit żądań Gemini. Sprawdź limity w Google AI Studio."
                ) from None
            if error.code == 404:
                raise ProviderUnavailableError(
                    "Gemini nie znalazło modelu (HTTP 404). Sprawdź nazwę modelu "
                    "i jego dostępność dla tego klucza."
                ) from None
            if error.code == 503:
                raise ProviderUnavailableError(
                    "Gemini jest chwilowo przeciążone lub niedostępne (HTTP 503). "
                    "Passat spróbował ponownie; odczekaj chwilę i wyślij wiadomość jeszcze raz."
                ) from None
            if error.code is not None:
                raise ProviderUnavailableError(
                    f"Gemini zwróciło błąd HTTP {error.code}. Sprawdź dostępność "
                    "modelu i status usługi Google AI."
                ) from None
            raise ProviderUnavailableError(
                "Gemini nie odpowiedziało poprawnie (bez kodu HTTP). "
                "Sprawdź połączenie i konfigurację modelu."
            ) from None
        except (httpx.HTTPError, TimeoutError, OSError):
            raise ProviderUnavailableError(
                "Nie udało się połączyć z Gemini. Sprawdź połączenie internetowe."
            ) from None
        except Exception:
            # Nie pokazuj ani nie loguj surowych błędów SDK, które mogą zawierać dane żądania.
            raise ProviderUnavailableError(
                "Gemini zwróciło nieoczekiwaną odpowiedź."
            ) from None

        if not reply or not reply.strip():
            raise ProviderUnavailableError("Gemini nie zwróciło tekstu odpowiedzi.")
        return reply.strip()
