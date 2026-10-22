"""Przygotowuje osobną, naturalną do odczytu wersję odpowiedzi dla Piper."""

from __future__ import annotations

import json
import re


_URL = re.compile(
    r"(?i)\b(?:(?:https?://|www\.)[^\s<>]+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>]*)?)"
)
_FENCED_CODE = re.compile(r"(?ms)^\s*(```|~~~).*?^\s*\1\s*$")
_INLINE_CODE = re.compile(r"(?<!`)`[^`\n]+`(?!`)")
_MARKDOWN_LINK = re.compile(r"!??\[([^\]]*)\]\([^)]*\)")
_REFERENCE_LINK = re.compile(r"!??\[([^\]]*)\]\[[^\]]*\]")
_EMPHASIS = re.compile(r"(?<!\w)(\*\*|__|\*|_|~~)(.+?)\1(?!\w)")


def _is_raw_json(line: str) -> bool:
    candidate = line.strip()
    if not candidate.startswith(("{", "[")):
        return False
    try:
        value = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(value, (dict, list))


def prepare_tts_text(text: str) -> str:
    """Usuwa składnię Markdown i nieczytelne bloki techniczne, zachowując sens.

    Funkcja nie modyfikuje tekstu wyświetlanego w czacie. Przy odpowiedzi złożonej
    wyłącznie z kodu lub JSON zwraca krótką zapowiedź zamiast literować znaki.
    """
    if not text or not text.strip():
        return ""

    had_code_block = bool(_FENCED_CODE.search(text))
    cleaned = _FENCED_CODE.sub(" Przykład kodu pomijam. ", text)
    cleaned = _MARKDOWN_LINK.sub(lambda match: match.group(1), cleaned)
    cleaned = _REFERENCE_LINK.sub(lambda match: match.group(1), cleaned)
    cleaned = _INLINE_CODE.sub("fragment kodu", cleaned)

    lines: list[str] = []
    had_json = False
    for line in cleaned.splitlines():
        if _is_raw_json(line):
            had_json = True
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s*>+\s?", "", line)
        line = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", line)
        line = re.sub(r"^\s*\[[ xX]\]\s+", "", line)
        if "|" in line and re.fullmatch(
            r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*", line
        ):
            continue
        if "|" in line and line.lstrip().startswith("|"):
            line = ", ".join(
                cell.strip() for cell in line.strip().strip("|").split("|")
            )
        if re.fullmatch(r"\s*(?:[-*_]\s*){3,}", line):
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = _EMPHASIS.sub(r"\2", cleaned)
    cleaned = re.sub(r"</?[A-Za-z][^>]*>", " ", cleaned)

    def remove_url(match: re.Match[str]) -> str:
        value = match.group(0)
        url = value.rstrip(".,!?;:)")
        return value[len(url) :]

    cleaned = _URL.sub(remove_url, cleaned)
    cleaned = re.sub(r":(?=\s*[.!?]?(?:\n|$))", "", cleaned)
    cleaned = re.sub(r"(?i)\bkm/h\b", "kilometrów na godzinę", cleaned)
    cleaned = re.sub(r"(?i)\bcm²\b", "centymetrów kwadratowych", cleaned)
    cleaned = re.sub(r"(?i)\bm²\b", "metrów kwadratowych", cleaned)
    cleaned = re.sub(r"(?i)\bcm³\b", "centymetrów sześciennych", cleaned)
    cleaned = re.sub(r"(?i)\bm³\b", "metrów sześciennych", cleaned)
    cleaned = re.sub(r"(?i)°\s*C\b", " stopni Celsjusza", cleaned)
    operand = r"([\wąćęłńóśźż]+|\))"
    right_operand = r"([\wąćęłńóśźż]+|\()"
    cleaned = re.sub(rf"{operand}\s*[×*]\s*{right_operand}", r"\1 razy \2", cleaned)
    cleaned = re.sub(rf"{operand}\s*[÷/]\s*{right_operand}", r"\1 podzielić przez \2", cleaned)
    cleaned = re.sub(rf"{operand}\s*=\s*{right_operand}", r"\1 równa się \2", cleaned)
    cleaned = re.sub(r"(?<=\d)\s*%", " procent", cleaned)
    # Pozostałe składniki składni (np. samotne znaczniki) nie powinny być mówione.
    cleaned = re.sub(r"(?m)^\s*\[[^\]]+\]:\s*\S+\s*$", "", cleaned)
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" +([,.;!?])", r"\1", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned.strip(" \n.,!?;:"):
        cleaned = ""

    if not cleaned:
        if had_json:
            return "Odpowiedź zawiera dane techniczne, których nie odczytam na głos."
        if had_code_block or "`" in text:
            return "Odpowiedź zawiera kod, którego nie odczytam na głos."
        return ""
    if had_json:
        cleaned = f"{cleaned}\nDane w formacie JSON pomijam."
    return cleaned
