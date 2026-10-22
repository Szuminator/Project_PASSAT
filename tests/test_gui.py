import threading
from threading import Event

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from main import PassatWindow
from passat.models import AssistantReply


class ImmediateSpeechService:
    def speak(self, _text, _stop_event, _on_started, _on_audio_level):
        return False


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
