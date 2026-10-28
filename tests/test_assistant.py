from collections.abc import Sequence
from datetime import datetime
from types import SimpleNamespace

import pytest

from passat.assistant import PassatAssistant
from passat.models import ChatMessage
from passat.providers.base import ProviderRateLimitError
from passat.providers.factory import ProviderSelection, create_provider
from passat.providers.offline import OfflineProvider
from passat.settings import Settings


def test_gemini_without_key_selects_honest_offline_provider():
    selection = create_provider(Settings(provider="gemini", gemini_api_key=""))
    assistant = PassatAssistant(selection)

    reply = assistant.handle_message("Cześć")

    assert reply.is_offline
    assert reply.provider_name == "offline"
    assert "trybie offline" in reply.text
    assert "Brak GEMINI_API_KEY" in assistant.startup_notice


def test_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("PASSAT_PROVIDER", "offline")
    monkeypatch.setenv("GEMINI_API_KEY", "example-only")
    monkeypatch.setenv("PASSAT_GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-example-only")
    monkeypatch.setenv("PASSAT_GROQ_MODEL", "qwen-test")
    monkeypatch.setenv("PASSAT_STT_MODEL", "base")
    monkeypatch.setenv("PASSAT_PIPER_MODEL", "voice/custom.onnx")
    monkeypatch.setenv("PASSAT_WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("PASSAT_WAKE_WORD_MODEL_PATH", "models/wake-test")
    monkeypatch.setenv("PASSAT_WAKE_WORD_MIN_CONFIDENCE", "0.4")
    monkeypatch.setenv("PASSAT_VAD_SILENCE_SECONDS", "1.1")
    monkeypatch.setenv("PASSAT_VAD_RMS_THRESHOLD", "0.006")
    monkeypatch.setenv("PASSAT_VAD_PRE_ROLL_MS", "300")

    settings = Settings.from_env()

    assert settings.provider == "offline"
    assert settings.gemini_api_key == "example-only"
    assert settings.gemini_model == "gemini-test"
    assert settings.groq_api_key == "groq-example-only"
    assert settings.groq_model == "qwen-test"
    assert settings.stt_model == "base"
    assert settings.piper_model == "voice/custom.onnx"
    assert settings.wake_word_enabled is True
    assert settings.wake_word_model_path == "models/wake-test"
    assert settings.wake_word_min_confidence == 0.4
    assert settings.vad_silence_seconds == 1.1
    assert settings.vad_rms_threshold == 0.006
    assert settings.vad_pre_roll_ms == 300


def test_offline_provider_handles_identity_mode_greeting_and_unknown():
    provider = OfflineProvider()

    assert "Cześć" in provider.generate_reply("Hej", (), "")
    assert "asystent samochodowy" in provider.generate_reply("Kim jesteś?", (), "")
    assert "trybie offline" in provider.generate_reply("W jakim trybie działasz?", (), "")
    assert "Jest teraz" in provider.generate_reply("Passat, jaka jest godzina?", (), "")
    assert "danych pogodowych" in provider.generate_reply("Podaj pogodę", (), "")


class RecordingProvider:
    name = "test"

    def __init__(self):
        self.calls: list[tuple[str, tuple[ChatMessage, ...], str]] = []

    def generate_reply(self, message, history: Sequence[ChatMessage], system_instruction):
        self.calls.append((message, tuple(history), system_instruction))
        return f"Odpowiedź {len(self.calls)}"


def test_history_is_bounded_and_message_is_not_sent_twice():
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    for index in range(12):
        assistant.handle_message(f"wiadomość {index}")

    assert [len(history) for _, history, _ in provider.calls] == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 20]
    assert len(assistant.history) == assistant.MAX_HISTORY_MESSAGES
    assert provider.calls[0][0] == "wiadomość 0"
    assert provider.calls[1][1] == (
        ChatMessage("user", "wiadomość 0"),
        ChatMessage("assistant", "Odpowiedź 1"),
    )
    assert provider.calls[-1][0] == "wiadomość 11"
    assert all(item.content != "wiadomość 11" for item in provider.calls[-1][1])
    assert sum(item.content == "wiadomość 11" for item in assistant.history) == 1


def test_gemini_failure_falls_back_once_without_duplicate_history():
    class LimitedProvider:
        name = "Gemini"

        def __init__(self):
            self.calls = 0

        def generate_reply(self, message, history, system_instruction):
            self.calls += 1
            raise ProviderRateLimitError("Osiągnięto limit żądań Gemini.")

    provider = LimitedProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "Gemini", False))

    reply = assistant.handle_message("Cześć")

    assert provider.calls == 1
    assert reply.is_offline
    assert reply.provider_name == "offline"
    assert "fallback" not in reply.text.lower()
    assert "tryb awaryjny offline" in reply.warning
    assert assistant.history == [
        ChatMessage("user", "Cześć"),
        ChatMessage("assistant", reply.text),
    ]


def test_local_time_question_skips_gemini_and_uses_local_clock():
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "Gemini", False))

    reply = assistant.handle_message("Passat, jak jest godzina?")

    assert "Jest teraz" in reply.text
    assert reply.provider_name == "offline"
    assert reply.is_offline
    assert reply.warning is None
    assert provider.calls == []


@pytest.mark.parametrize(
    "message",
    [
        "Passat, jaka jest godzina?",
        "Hej, która teraz godzina?",
        "Która jest teraz godzina?",
        "Podaj mi aktualną godzinę.",
        "Masz godzinę?",
        "Powiedz mi, która jest godzina.",
        "Jaka jest lokalna godzina?",
    ],
)
def test_common_current_time_phrasings_are_answered_locally(message):
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    reply = assistant.handle_message(message)

    assert reply.text.startswith("Jest teraz ")
    assert reply.provider_name == "offline"
    assert provider.calls == []


@pytest.mark.parametrize(
    "message",
    [
        "Ile godzin trwa podróż?",
        "Jaka jest godzina otwarcia sklepu?",
        "Podaj godzinę spotkania.",
        "Co oznacza słowo godzina?",
    ],
)
def test_non_current_time_questions_are_not_answered_with_local_clock(message):
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    reply = assistant.handle_message(message)

    assert reply.provider_name == "test"
    assert provider.calls[0][0] == message


def test_current_date_is_formatted_in_polish_and_skips_provider(monkeypatch):
    local_timezone = datetime.now().astimezone().tzinfo
    fixed_now = datetime(2026, 10, 28, 12, 0, tzinfo=local_timezone)
    monkeypatch.setattr(
        "passat.providers.offline.datetime",
        SimpleNamespace(now=lambda: fixed_now),
    )
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    for message in (
        "Passat, jaka jest dzisiaj data?",
        "Jaki mamy dzisiaj dzień?",
        "Podaj dzisiejszą datę.",
        "Która jest dzisiaj data?",
    ):
        reply = assistant.handle_message(message)
        assert reply.text == "Dzisiaj jest środa, 28 października 2026 roku."
        assert reply.provider_name == "offline"

    assert provider.calls == []


@pytest.mark.parametrize(
    "message",
    [
        "Jaka jest data spotkania?",
        "Podaj datę premiery filmu.",
        "Co wydarzyło się dzisiaj?",
    ],
)
def test_non_current_date_questions_are_not_answered_with_system_date(message):
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    reply = assistant.handle_message(message)

    assert reply.provider_name == "test"
    assert provider.calls[0][0] == message


def test_empty_message_does_not_reach_provider():
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    with pytest.raises(ValueError):
        assistant.handle_message("   ")

    assert provider.calls == []


@pytest.mark.parametrize(
    "message",
    [
        "Wyznacz trasę do najbliższego burdelu.",
        "Wyznacz trasę do burdelu.",
        "Ustaw nawigację na kurwy.",
        "Jak dojechać do kurwiarni?",
        "Jak mam dojechać do burdelu?",
        "Chcę dojechać na kurwy.",
        "Jak najłatwiej trafić do domu publicznego?",
        "Potrzebuję trasy do burdelu.",
        "Pokaż drogę do agencji towarzyskiej.",
        "Zaplanuj trasę do domu publicznego.",
        "Nawiguj na kury.",  # typowa pomyłka rozpoznawania „kurwy”
        "Ustaw cel podróży: lupanar.",
    ],
)
def test_route_easter_egg_is_deterministic_and_skips_provider(message):
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    reply = assistant.handle_message(message)

    assert reply.text == "Nie znam dokładnego adresu tego miejsca."
    assert reply.provider_name == "reguła lokalna"
    assert reply.is_local_rule is True
    assert reply.is_offline is False
    assert provider.calls == []
    assert assistant.history == [
        ChatMessage("user", message),
        ChatMessage("assistant", reply.text),
    ]


@pytest.mark.parametrize(
    "message",
    [
        "Co oznacza słowo burdel?",
        "Jak odmienić słowo kurwy?",
        "Wyznacz trasę do Krakowa.",
        "Wyznacz trasę do najbliższego hotelu.",
        "Pokaż drogę do Warszawy i opowiedz, co znaczy burdel.",
    ],
)
def test_route_easter_egg_ignores_word_meanings_and_other_destinations(message):
    provider = RecordingProvider()
    assistant = PassatAssistant(ProviderSelection(provider, "test", False))

    reply = assistant.handle_message(message)

    assert reply.is_local_rule is False
    assert provider.calls[0][0] == message
