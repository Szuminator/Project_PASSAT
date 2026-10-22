"""Proste, jawnie ograniczone odpowiedzi działające bez modelu językowego."""

import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime

from passat.models import ChatMessage
from passat.providers.base import BaseAIProvider


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


class OfflineProvider(BaseAIProvider):
    name = "offline"

    @staticmethod
    def can_answer_locally(message: str) -> bool:
        """Zwraca True, gdy odpowiedź nie wymaga modelu ani internetu."""
        text = _normalize(message).strip()
        return any(
            phrase in text
            for phrase in (
                "jaka jest godzina",
                "jak jest godzina",
                "ktora godzina",
                "podaj godzine",
                "lokalna godzina",
                "godzina lokalna",
            )
        )

    def generate_reply(
        self,
        message: str,
        history: Sequence[ChatMessage],
        system_instruction: str,
    ) -> str:
        del history, system_instruction
        text = _normalize(message).strip()

        if self.can_answer_locally(text):
            current_time = datetime.now().astimezone().strftime("%H:%M")
            return f"Jest teraz {current_time} czasu lokalnego."

        if any(phrase in text for phrase in ("pogod", "temperatura", "bedzie padac", "opad")):
            return (
                "Nie mam teraz dostępu do aktualnych danych pogodowych. "
                "Moduł pogody nie jest jeszcze podłączony, więc nie chcę zgadywać."
            )

        if re.fullmatch(r"(czesc|hej|witaj|siema|dzien dobry|dobry wieczor)[.!? ]*", text):
            return "Cześć. Działam w trybie offline. W czym mogę pomóc?"

        if any(phrase in text for phrase in ("kim jest passat", "kim jestes", "kim jestes passat", "co to jest passat")):
            return (
                "Jestem Passat, Twój asystent samochodowy. Teraz działam w trybie "
                "offline, więc moje możliwości są ograniczone."
            )

        if any(phrase in text for phrase in ("w jakim trybie", "jaki tryb", "czy jestes online", "aktualny tryb")):
            return "Jestem teraz w trybie offline. Nie korzystam z modelu AI."

        return (
            "Nie mam teraz dostępu do modelu AI, więc nie potrafię rzetelnie "
            "odpowiedzieć. Mogę podać lokalną godzinę, rozpoznać proste "
            "powitanie albo opowiedzieć, kim jest Passat."
        )
