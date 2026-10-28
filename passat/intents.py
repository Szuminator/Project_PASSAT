"""Proste, deterministyczne intencje obsługiwane lokalnie przed wywołaniem AI."""

from __future__ import annotations

import re
import unicodedata


ROUTE_EASTER_EGG_REPLY = "Nie znam dokładnego adresu tego miejsca."


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks.replace("ł", "l")).strip()


_PLACE = (
    r"(?:burdel\w*|bordel\w*|kurw\w*|kurwiarni\w*|dziwk\w*|"
    r"prostytut\w*|lupanar\w*|dom\w* publiczn\w*|dom schadzek|"
    r"agencj\w+ towarzysk\w*|kury)"
)
_DESTINATION_MODIFIERS = (
    r"(?:(?:najblizsz\w*|poblisk\w*|blisk\w*|jakis\w*|"
    r"jakieg\w*|jakiej\w*|lokaln\w*)\s+){0,2}"
)
_PLACE_WITH_MODIFIERS = rf"{_DESTINATION_MODIFIERS}{_PLACE}"
_DESTINATION = (
    rf"\b(?:do|na|pod|w okolice|w kierunku)\s+"
    rf"{_PLACE_WITH_MODIFIERS}\b"
)
_ROUTE_ACTION = (
    r"(?:wyznacz\w*|ustaw\w*|zaplanuj\w*|znajdz\w*|wytycz\w*|"
    r"pokaz\w*|podaj\w*|przygotuj\w*|oblicz\w*|zrob\w*|"
    r"poprowadz\w*|prowadz\w*|nawig\w*|uruchom\w*|daj\w*|"
    r"jedz\w*|jech\w*|pojedz\w*|"
    r"jak(?:\s+\w+){0,4}\s+(?:dojechac|trafic|dotrzec)|"
    r"chce(?:\s+\w+){0,2}\s+(?:dojechac|trafic|dotrzec))"
)

_ACTION_WITH_DESTINATION = re.compile(
    rf"\b{_ROUTE_ACTION}\b.{{0,100}}?{_DESTINATION}\b"
)
_ROUTE_NOUN_WITH_DESTINATION = re.compile(
    rf"\b(?:tras\w*|drog\w*|nawigacj\w*|dojazd\w*)\b"
    rf".{{0,40}}?{_DESTINATION}\b"
)
_SET_DESTINATION = re.compile(
    rf"\b(?:ustaw|wybierz|wpisz|dodaj)\w*\b.{{0,35}}?"
    rf"\b(?:cel|miejsce docelowe)\b.{{0,20}}?\b{_PLACE_WITH_MODIFIERS}\b"
)


def is_route_easter_egg_request(message: str) -> bool:
    """Rozpoznaje trasę do określonego rodzaju miejsca, nie samo słowo o nim."""
    text = _normalize(message)
    return bool(
        _ACTION_WITH_DESTINATION.search(text)
        or _ROUTE_NOUN_WITH_DESTINATION.search(text)
        or _SET_DESTINATION.search(text)
    )
