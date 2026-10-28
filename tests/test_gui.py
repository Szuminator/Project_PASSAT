import threading
from datetime import datetime
from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from main import PassatWindow
from passat.assistant import PassatAssistant
from passat.models import AssistantReply
from passat.providers.factory import ProviderSelection


class ImmediateSpeechService:
    def speak(self, _text, _stop_event, _on_started, _on_audio_level):
        return False


class ControlledSpeechServiceForWakeTest:
    def __init__(self):
        self.started = Event()

    def speak(self, _text, stop_event, on_started, on_audio_level):
        on_started()
        on_audio_level(0.4)
        self.started.set()
        stop_event.wait(timeout=2)
        on_audio_level(0.0)
        return stop_event.is_set()


class BlockingAssistant:
    is_offline = False
    startup_notice = None
    provider_name = "Gemini"

    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.messages = []

    def handle_message(self, message):
        self.messages.append(message)
        self.started.set()
        self.release.wait(timeout=3)
        return AssistantReply("Gotowe.", "Gemini", False)


def test_gui_remains_responsive_while_provider_waits(qapp):
    assistant = BlockingAssistant()
    window = PassatWindow(assistant=assistant)
    window.speech_output_service = ImmediateSpeechService()
    window.show()
    window.message_input.setText("Cześć Passat")

    window.send_button.click()

    assert assistant.started.wait(timeout=1)
    assert window.status_label.text().endswith("MYŚLĘ")
    assert not window.send_button.isEnabled()
    assert "TY: Cześć Passat" in window.chat.toPlainText()
    assert assistant.messages == ["Cześć Passat"]

    assistant.release.set()
    for _ in range(100):
        QTest.qWait(20)
        if "PASSAT (Gemini): Gotowe." in window.chat.toPlainText() and window.send_button.isEnabled():
            break

    assert "PASSAT (Gemini): Gotowe." in window.chat.toPlainText()
    assert window.status_label.text().endswith("GOTOWY")
    assert window.send_button.isEnabled()
    assert window.chat.toPlainText().count("TY: Cześć Passat") == 1
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_enter_key_sends_message_and_offline_reply_sets_offline_status(qapp):
    class ImmediateOfflineAssistant:
        is_offline = True
        startup_notice = None

        def __init__(self):
            self.messages = []

        def handle_message(self, message):
            self.messages.append(message)
            return AssistantReply("Tryb awaryjny.", "offline", True)

    assistant = ImmediateOfflineAssistant()
    window = PassatWindow(assistant=assistant)
    window.speech_output_service = ImmediateSpeechService()
    window.show()
    window.message_input.setText("W jakim trybie jesteś?")
    QTest.keyClick(window.message_input, Qt.Key.Key_Return)

    for _ in range(100):
        QTest.qWait(20)
        if "PASSAT (offline): Tryb awaryjny." in window.chat.toPlainText() and window.send_button.isEnabled():
            break

    assert assistant.messages == ["W jakim trybie jesteś?"]
    assert window.status_label.text().endswith("OFFLINE")
    assert "Dostawca: OFFLINE" in window.provider_label.text()
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_real_window_starts_and_answers_in_selected_offline_mode(qapp, monkeypatch):
    monkeypatch.setenv("PASSAT_PROVIDER", "offline")
    window = PassatWindow()
    window.speech_output_service = ImmediateSpeechService()
    window.show()
    assert window.status_label.text().endswith("OFFLINE")
    assert "Dostawca: OFFLINE" in window.provider_label.text()

    window.message_input.setText("Cześć")
    window.send_button.click()
    for _ in range(100):
        QTest.qWait(20)
        if "PASSAT (offline):" in window.chat.toPlainText() and window.send_button.isEnabled():
            break

    assert "PASSAT (offline):" in window.chat.toPlainText()
    assert window.status_label.text().endswith("OFFLINE")
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_voice_transcript_enters_existing_assistant_once_and_gui_stays_responsive(qapp):
    class RecordingAssistant:
        is_offline = False
        provider_name = "GroqCloud"
        startup_notice = None

        def __init__(self):
            self.messages = []
            self.started = Event()
            self.release = Event()

        def handle_message(self, message):
            self.messages.append(message)
            self.started.set()
            self.release.wait(timeout=2)
            return AssistantReply("Odpowiedź tekstowa.", "GroqCloud", False)

    class FakeVoiceInputService:
        def __init__(self):
            self.started = Event()

        def record(self, stop_event):
            self.started.set()
            stop_event.wait(timeout=2)
            return object()

        def transcribe(self, _audio):
            return "Ile to jest dwa plus dwa?"

    assistant = RecordingAssistant()
    window = PassatWindow(assistant=assistant)
    window.voice_input_service = FakeVoiceInputService()
    window.speech_output_service = ImmediateSpeechService()
    window.show()

    window.microphone_button.click()
    assert window.status_label.text().endswith("SŁUCHAM")
    assert window.voice_input_service.started.wait(timeout=1)
    QTest.qWait(30)
    assert window.status_label.text().endswith("SŁUCHAM")

    window.microphone_button.click()
    for _ in range(50):
        QTest.qWait(20)
        if assistant.started.is_set():
            break
    assert assistant.started.is_set()
    assert assistant.messages == ["Ile to jest dwa plus dwa?"]
    assert "TY: Ile to jest dwa plus dwa?" in window.chat.toPlainText()

    assistant.release.set()
    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled():
            break

    assert assistant.messages == ["Ile to jest dwa plus dwa?"]
    assert window.status_label.text().endswith("GOTOWY")
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_speaking_status_follows_playback_and_stop_restores_ready(qapp):
    class ImmediateAssistant:
        is_offline = False
        provider_name = "GroqCloud"
        startup_notice = None

        def handle_message(self, _message):
            return AssistantReply("Odpowiedź do odczytania.", "GroqCloud", False)

    class ControlledSpeechService:
        def __init__(self):
            self.started = Event()

        def speak(self, _text, stop_event, on_started, on_audio_level):
            on_started()
            on_audio_level(0.65)
            self.started.set()
            stop_event.wait(timeout=2)
            on_audio_level(0.0)
            return stop_event.is_set()

    window = PassatWindow(assistant=ImmediateAssistant())
    speech_service = ControlledSpeechService()
    window.speech_output_service = speech_service
    window.show()
    window.message_input.setText("Przeczytaj odpowiedź")
    window.send_button.click()

    for _ in range(50):
        QTest.qWait(20)
        if (
            speech_service.started.is_set()
            and window.status_label.text().endswith("MÓWIĘ")
            and window.core._audio_level > 0
        ):
            break
    assert speech_service.started.is_set()
    assert window.status_label.text().endswith("MÓWIĘ")
    assert not window.send_button.isEnabled()
    assert window.core._audio_level == 0.65

    window.stop_speech_button.click()
    for _ in range(50):
        QTest.qWait(20)
        if window.send_button.isEnabled():
            break

    assert window.status_label.text().endswith("GOTOWY")
    assert window.core._audio_level == 0.0
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_wake_listener_resumes_only_after_piper_finishes(qapp, monkeypatch):
    class ImmediateAssistant:
        is_offline = False
        provider_name = "GroqCloud"
        startup_notice = None

        def handle_message(self, _message):
            return AssistantReply("Odpowiedź do odczytania.", "GroqCloud", False)

    speech_service = ControlledSpeechServiceForWakeTest()
    window = PassatWindow(assistant=ImmediateAssistant())
    window.speech_output_service = speech_service
    window._wake_enabled = True
    wake_starts = []
    monkeypatch.setattr(window, "_start_wake_word_listener", lambda: wake_starts.append(True))
    window.show()
    window.message_input.setText("test odpowiedzi głosowej")
    window.send_button.click()

    for _ in range(100):
        QTest.qWait(20)
        if speech_service.started.is_set() and window.status_label.text().endswith("MÓWIĘ"):
            break
    assert speech_service.started.is_set()
    assert window.status_label.text().endswith("MÓWIĘ")
    assert wake_starts == []

    window.stop_speech_button.click()
    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled():
            break

    assert wake_starts == [True]
    window._wake_enabled = False
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_local_rule_reply_is_not_reported_as_a_provider_call(qapp):
    class LocalRuleAssistant:
        is_offline = False
        startup_notice = None
        provider_name = "GroqCloud"

        def handle_message(self, _message):
            return AssistantReply(
                "Nie znam dokładnego adresu tego miejsca.",
                "reguła lokalna",
                False,
                is_local_rule=True,
            )

    window = PassatWindow(assistant=LocalRuleAssistant())
    window.speech_output_service = ImmediateSpeechService()
    window.show()
    window.message_input.setText("wyznacz trasę do celu")
    window.send_button.click()

    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled():
            break

    assert "PASSAT (reguła lokalna): Nie znam dokładnego adresu tego miejsca." in (
        window.chat.toPlainText()
    )
    assert window.provider_label.text() == "Odpowiedź lokalna · bez wywołania modelu"
    assert window.status_label.text().endswith("GOTOWY")
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_whisper_time_transcript_uses_local_clock_without_provider(qapp):
    class ProviderSpy:
        name = "test-provider"

        def __init__(self):
            self.calls = []

        def generate_reply(self, message, _history, _system_instruction):
            self.calls.append(message)
            return "To nie powinno się pojawić."

    provider = ProviderSpy()
    assistant = PassatAssistant(ProviderSelection(provider, "test-provider", False))
    window = PassatWindow(assistant=assistant)
    window.speech_output_service = ImmediateSpeechService()
    window.show()

    window._on_transcription("Passat, która teraz jest godzina?")
    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled() and "PASSAT (offline): Jest teraz " in window.chat.toPlainText():
            break

    assert "PASSAT (offline): Jest teraz " in window.chat.toPlainText()
    assert provider.calls == []
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_whisper_date_transcript_uses_system_date_without_provider(qapp, monkeypatch):
    local_timezone = datetime.now().astimezone().tzinfo
    fixed_now = datetime(2026, 10, 28, 12, 0, tzinfo=local_timezone)
    monkeypatch.setattr(
        "passat.providers.offline.datetime",
        SimpleNamespace(now=lambda: fixed_now),
    )

    class ProviderSpy:
        name = "test-provider"

        def __init__(self):
            self.calls = []

        def generate_reply(self, message, _history, _system_instruction):
            self.calls.append(message)
            return "Provider nie powinien określać daty."

    provider = ProviderSpy()
    assistant = PassatAssistant(ProviderSelection(provider, "test-provider", False))
    window = PassatWindow(assistant=assistant)
    window.speech_output_service = ImmediateSpeechService()
    window.show()

    window._on_transcription("Passat, jaka jest dzisiaj data?")
    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled() and "Dzisiaj jest środa" in window.chat.toPlainText():
            break

    assert "Dzisiaj jest środa, 28 października 2026 roku." in window.chat.toPlainText()
    assert provider.calls == []
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_route_rule_is_shared_by_typed_and_whisper_messages(qapp):
    class ProviderSpy:
        name = "test-provider"

        def __init__(self):
            self.calls = []

        def generate_reply(self, message, _history, _system_instruction):
            self.calls.append(message)
            return "Provider nie powinien dostać tej wiadomości."

    provider = ProviderSpy()
    assistant = PassatAssistant(ProviderSelection(provider, "test-provider", False))
    window = PassatWindow(assistant=assistant)
    window.speech_output_service = ImmediateSpeechService()
    window.show()

    window.message_input.setText("Ustaw trasę na burdel.")
    window.send_button.click()
    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled() and window.chat.toPlainText().count("reguła lokalna") >= 1:
            break

    assert "Nie znam dokładnego adresu tego miejsca." in window.chat.toPlainText()
    assert provider.calls == []

    # _on_transcription jest wspólną ścieżką sygnału z Whispera i ręcznego mikrofonu.
    window._on_transcription("Jak mam dojechać do burdelu?")
    for _ in range(100):
        QTest.qWait(20)
        if window.send_button.isEnabled() and window.chat.toPlainText().count("reguła lokalna") >= 2:
            break

    assert window.chat.toPlainText().count("Nie znam dokładnego adresu tego miejsca.") == 2
    assert provider.calls == []
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_chat_keeps_markdown_but_piper_gets_prepared_text(qapp):
    class MarkdownAssistant:
        is_offline = False
        provider_name = "GroqCloud"
        startup_notice = None

        def handle_message(self, _message):
            return AssistantReply(
                "# **Ważne**\n- Otwórz [dokument](https://example.com).\n"
                "```python\nprint('sekret')\n```",
                "GroqCloud",
                False,
            )

    class CapturingSpeechService:
        def __init__(self):
            self.text = None

        def speak(self, text, _stop_event, on_started, _on_audio_level):
            self.text = text
            on_started()
            return False

    speech = CapturingSpeechService()
    window = PassatWindow(assistant=MarkdownAssistant())
    window.speech_output_service = speech
    window.show()
    window.message_input.setText("test Markdown")
    window.send_button.click()

    for _ in range(100):
        QTest.qWait(20)
        if speech.text is not None and window.send_button.isEnabled():
            break

    visible = window.chat.toPlainText()
    assert "# **Ważne**" in visible
    assert "[dokument](https://example.com)" in visible
    assert "print('sekret')" in visible
    assert speech.text == "Ważne\nOtwórz dokument.\nPrzykład kodu pomijam."
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_wake_listening_can_be_toggled_and_is_blocked_while_speaking(qapp, monkeypatch):
    window = PassatWindow(assistant=BlockingAssistant())
    window.show()
    shutdown = Event()
    window._wake_shutdown_event = shutdown
    window._wake_enabled = True

    window.toggle_wake_word()

    assert not window._wake_enabled
    assert shutdown.is_set()
    assert window.wake_word_button.text() == "WŁĄCZ NASŁUCH HASŁA"

    starts = []
    monkeypatch.setattr(window, "_start_wake_word_listener", lambda: starts.append(True))
    original_start_listener = PassatWindow._start_wake_word_listener
    window.toggle_wake_word()
    assert window._wake_enabled
    assert starts == [True]

    window._wake_word_worker = None
    window._speaking = True
    original_start_listener(window)
    assert starts == [True]
    window._speaking = False
    window._wake_enabled = False
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_missing_wake_model_keeps_manual_microphone_available(qapp, monkeypatch):
    monkeypatch.setenv("PASSAT_WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("PASSAT_WAKE_WORD_MODEL_PATH", "models/not-installed-yet")
    window = PassatWindow(assistant=BlockingAssistant())
    window.show()

    for _ in range(100):
        QTest.qWait(20)
        if (
            "Nasłuch hasła wyłączony" in window.chat.toPlainText()
            and window._wake_word_worker is None
        ):
            break

    assert "Nasłuch hasła wyłączony" in window.chat.toPlainText()
    assert not window._wake_enabled
    assert window.microphone_button.isEnabled()
    assert window.microphone_button.text() == "ROZPOCZNIJ MÓWIENIE"
    window.close()
    assert window._thread_pool.waitForDone(1000)
