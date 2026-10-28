"""Proste, jawnie ograniczone odpowiedzi działające bez modelu językowego."""

import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime

from passat.models import ChatMessage
from passat.providers.base import BaseAIProvider


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks.replace("ł", "l")).strip()


_TIME_WORD = r"(?:godzin\w*|czas)"
_CURRENT_TIME_QUESTION = re.compile(
    rf"(?:\b(?:jaka|ktora)\b"
    rf"(?:\s+(?:jest|teraz|aktualnie|obecnie|lokalnie|mamy|to)){{0,3}}"
    rf"\s+\b{_TIME_WORD}\b|"
    rf"\bjak(?:\s+(?:jest|teraz|aktualnie|obecnie)){{1,3}}\s+\b{_TIME_WORD}\b)"
)
_CURRENT_TIME_REQUEST = re.compile(
    rf"\b(?:podaj|powiedz|sprawdz|pokaz|znasz|wiesz|masz)\b"
    rf".{{0,45}}?\b{_TIME_WORD}\b"
)
_NON_CURRENT_TIME_CONTEXT = re.compile(
    r"\b(?:otwarci\w*|zamknieci\w*|odjazd\w*|przyjazd\w*|"
    r"spotkan\w*|wydarzen\w*|seans\w*|lekcj\w*|zakonczen\w*|"
    r"definicj\w*|znaczeni\w*|trwania)\b"
)
_CURRENT_DATE_QUESTION = re.compile(
    r"\b(?:jaka|ktora)\b.{0,35}\bdat\w*\b|"
    r"\b(?:jaki|ktory)\b.{0,35}\b(?:dzien|dat\w*)\b|"
    r"\b(?:podaj|powiedz|sprawdz|pokaz|znasz|wiesz)\b.{0,45}\bdat\w*\b|"
    r"\b(?:dzis|dzisiaj|dzisiejsz\w*)\b.{0,25}\b(?:dat\w*|dzien)\b|"
    r"\b(?:dat\w*|dzien)\b.{0,25}\b(?:dzis|dzisiaj)\b|"
    r"\b(?:ktory|jaki)\s+(?:mamy|jest)\s+(?:dzis|dzisiaj)\b"
)
_NON_CURRENT_DATE_CONTEXT = re.compile(
    r"\b(?:spotkan\w*|urodzin\w*|faktur\w*|dokument\w*|premier\w*|"
    r"wydarzen\w*|waznosci|wyjazd\w*|przyjazd\w*|bitw\w*|"
    r"historycz\w*|wydan\w*|publikac\w*)\b"
)
_POLISH_WEEKDAYS = (
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "sobota",
    "niedziela",
)
_POLISH_MONTHS = (
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
)


def _is_current_time_question(text: str) -> bool:
    if _NON_CURRENT_TIME_CONTEXT.search(text):
        return False
    return bool(
        _CURRENT_TIME_QUESTION.search(text)
        or _CURRENT_TIME_REQUEST.search(text)
        or re.search(r"\b(?:lokalna|aktualna)\s+godzin\w*\b", text)
        or re.search(r"\b(?:godzin\w*\s+lokaln\w*|czas\s+lokaln\w*)\b", text)
    )


def _is_current_date_question(text: str) -> bool:
    if _NON_CURRENT_DATE_CONTEXT.search(text):
        return False
    return bool(_CURRENT_DATE_QUESTION.search(text))


def _format_polish_date(value: datetime) -> str:
    weekday = _POLISH_WEEKDAYS[value.weekday()]
    month = _POLISH_MONTHS[value.month - 1]
    return f"Dzisiaj jest {weekday}, {value.day} {month} {value.year} roku."


class OfflineProvider(BaseAIProvider):
    name = "offline"

    @staticmethod
    def can_answer_locally(message: str) -> bool:
        """Zwraca True, gdy odpowiedź nie wymaga modelu ani internetu."""
        text = _normalize(message).strip()
        return _is_current_time_question(text) or _is_current_date_question(text)

    def generate_reply(
        self,
        message: str,
        history: Sequence[ChatMessage],
        system_instruction: str,
    ) -> str:
        del history, system_instruction
        text = _normalize(message).strip()

        asks_time = _is_current_time_question(text)
        asks_date = _is_current_date_question(text)
        if asks_time or asks_date:
            now = datetime.now().astimezone()
            if asks_time and asks_date:
                current_time = now.strftime("%H:%M")
                return f"{_format_polish_date(now)} Jest teraz {current_time} czasu lokalnego."
            if asks_date:
                return _format_polish_date(now)
            current_time = now.strftime("%H:%M")
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
            "odpowiedzieć. Mogę podać lokalną godzinę i dzisiejszą datę, rozpoznać proste "
            "powitanie albo opowiedzieć, kim jest Passat."
        )
