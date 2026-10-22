from threading import Event

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from main import PassatWindow
from passat.models import AssistantReply


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
    window.show()
    window.message_input.setText("Cześć Passat")

    window.send_button.click()

    assert assistant.started.wait(timeout=1)
    assert window.status_label.text().endswith("MYŚLĘ")
    assert not window.send_button.isEnabled()
    assert "TY: Cześć Passat" in window.chat.toPlainText()
    assert assistant.messages == ["Cześć Passat"]

    assistant.release.set()
    for _ in range(30):
        QTest.qWait(20)
        if "PASSAT (Gemini): Gotowe." in window.chat.toPlainText():
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
    window.show()
    window.message_input.setText("W jakim trybie jesteś?")
    QTest.keyClick(window.message_input, Qt.Key.Key_Return)

    for _ in range(30):
        QTest.qWait(20)
        if "PASSAT (offline): Tryb awaryjny." in window.chat.toPlainText():
            break

    assert assistant.messages == ["W jakim trybie jesteś?"]
    assert window.status_label.text().endswith("OFFLINE")
    assert "Dostawca: OFFLINE" in window.provider_label.text()
    window.close()
    assert window._thread_pool.waitForDone(1000)


def test_real_window_starts_and_answers_in_selected_offline_mode(qapp, monkeypatch):
    monkeypatch.setenv("PASSAT_PROVIDER", "offline")
    window = PassatWindow()
    window.show()
    assert window.status_label.text().endswith("OFFLINE")
    assert "Dostawca: OFFLINE" in window.provider_label.text()

    window.message_input.setText("Cześć")
    window.send_button.click()
    for _ in range(30):
        QTest.qWait(20)
        if "PASSAT (offline):" in window.chat.toPlainText():
            break

    assert "PASSAT (offline):" in window.chat.toPlainText()
    assert window.status_label.text().endswith("OFFLINE")
    window.close()
    assert window._thread_pool.waitForDone(1000)
