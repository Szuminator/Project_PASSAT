from passat.audio.tts_text import prepare_tts_text


def test_tts_removes_bold_italic_and_heading_markers():
    assert prepare_tts_text("# **Ważne** i *sprawdzone*") == "Ważne i sprawdzone"


def test_tts_removes_bullet_and_numbered_list_prefixes():
    text = "- pierwszy punkt\n2. drugi punkt"
    assert prepare_tts_text(text) == "pierwszy punkt\ndrugi punkt"
    assert prepare_tts_text("| model | rok |\n| --- | --- |\n| B6 | 2008 |") == (
        "model, rok\nB6, 2008"
    )


def test_tts_keeps_link_label_but_omits_url():
    assert prepare_tts_text("[dokument](https://example.com/a?b=c).") == "dokument."
    assert prepare_tts_text("Szczegóły: example.com/plik.") == "Szczegóły."


def test_tts_does_not_read_code_and_uses_notice_for_code_only():
    assert prepare_tts_text("Uruchom `print('Hej')` teraz.") == (
        "Uruchom fragment kodu teraz."
    )
    assert prepare_tts_text("```python\nprint('Hej')\n```") == "Przykład kodu pomijam."


def test_tts_skips_raw_json_instead_of_reading_symbols():
    assert prepare_tts_text('{"ok": true}') == (
        "Odpowiedź zawiera dane techniczne, których nie odczytam na głos."
    )


def test_tts_empty_text_stays_empty_and_polish_text_is_preserved():
    assert prepare_tts_text(" \n ") == ""
    assert prepare_tts_text("Zażółć gęślą jaźń. Łódź, źdźbło.") == (
        "Zażółć gęślą jaźń. Łódź, źdźbło."
    )


def test_tts_keeps_math_operators_and_units():
    assert prepare_tts_text("Pole to (a * h) / 2, czyli 3,5 m².") == (
        "Pole to (a razy h) podzielić przez 2, czyli 3,5 metrów kwadratowych."
    )
    assert prepare_tts_text("Jedź z prędkością 50 km/h, nie 70°C.") == (
        "Jedź z prędkością 50 kilometrów na godzinę, nie 70 stopni Celsjusza."
    )
