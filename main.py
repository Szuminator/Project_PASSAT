"""Punkt startowy Passata i widok rozmowy w PySide6."""

import sys
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core_widget import CoreWidget
from passat.assistant import PassatAssistant
from passat.audio.input import VoiceInputService, VoiceInputWorker
from passat.audio.output import PiperSpeechService, SpeechOutputWorker
from passat.audio.tts_text import prepare_tts_text
from passat.audio.wake_word import WakeWordWorker
from passat.models import AssistantReply
from passat.providers.base import ProviderConfigurationError
from passat.providers.factory import ProviderSelection, create_provider
from passat.providers.offline import OfflineProvider
from passat.settings import Settings


def create_assistant() -> PassatAssistant:
    """Wybiera dostawcę z konfiguracji i bezpiecznie obsługuje błędne ustawienie."""
    try:
        selection = create_provider(Settings.from_env())
    except ProviderConfigurationError as error:
        selection = ProviderSelection(
            provider=OfflineProvider(),
            provider_name="offline",
            is_offline=True,
            notice=f"{error} Passat działa w trybie offline.",
        )
    return PassatAssistant(selection)


class ReplySignals(QObject):
    completed = Signal(object)
    failed = Signal()


class ReplyWorker(QRunnable):
    """Uruchamia komunikację z dostawcą poza wątkiem interfejsu."""

    def __init__(self, assistant: PassatAssistant, message: str):
        super().__init__()
        self.assistant = assistant
        self.message = message
        self.signals = ReplySignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.completed.emit(self.assistant.handle_message(self.message))
        except Exception:
            # Nie przekazujemy do GUI surowego wyjątku, który mógłby zawierać dane żądania.
            self.signals.failed.emit()


class PassatWindow(QMainWindow):
    """Okno Passata, czat i testowe sterowanie animacją."""

    STATUSES = ("GOTOWY", "SŁUCHAM", "MYŚLĘ", "MÓWIĘ", "OFFLINE")

    def __init__(self, assistant: PassatAssistant | None = None):
        super().__init__()
        self.assistant = assistant or create_assistant()
        self.settings = Settings.from_env()
        self.voice_input_service = VoiceInputService(self.settings.stt_model)
        self.speech_output_service = PiperSpeechService(self.settings.piper_model)
        self._thread_pool = QThreadPool(self)
        self._active_worker: ReplyWorker | None = None
        self._voice_input_worker: VoiceInputWorker | None = None
        self._wake_word_worker: WakeWordWorker | None = None
        self._wake_engine = None
        self._speech_output_worker: SpeechOutputWorker | None = None
        self._voice_stop_event: threading.Event | None = None
        self._wake_shutdown_event: threading.Event | None = None
        self._wake_manual_record_event: threading.Event | None = None
        self._wake_enabled = self.settings.wake_word_enabled
        self._pending_speech_text: str | None = None
        self._speech_stop_event: threading.Event | None = None
        self._sending = False
        self._recording = False
        self._speaking = False
        self._shutdown_waiting = False
        self._reply_is_offline = self.assistant.is_offline

        self.setWindowTitle("PASSAT — osobisty asystent jazdy")
        self.resize(980, 900)
        self.setMinimumSize(760, 780)
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #080d16; color: #e8f2ff; }
            QLabel#brand { color: #eaf5ff; font-size: 28px; font-weight: 700; letter-spacing: 12px; }
            QLabel#tagline { color: #72839d; font-size: 11px; letter-spacing: 3px; }
            QLabel#status { color: #69dfff; font-size: 13px; font-weight: 700; letter-spacing: 3px;
                            background: #102033; border: 1px solid #1d526a; border-radius: 14px;
                            padding: 9px 18px; }
            QLabel#hint, QLabel#provider { color: #8191a8; font-size: 11px; letter-spacing: 1px; }
            QPlainTextEdit#chat { color: #d9e5f4; background: #0c1420; border: 1px solid #1b2b40;
                                  border-radius: 12px; padding: 12px; font-size: 13px; }
            QLineEdit#message { color: #e8f2ff; background: #0c1420; border: 1px solid #263b54;
                                border-radius: 10px; padding: 12px; font-size: 13px; }
            QLineEdit#message:focus { border-color: #39afd0; }
            QPushButton { color: #b8c8dc; background: #101a29; border: 1px solid #203149;
                          border-radius: 10px; padding: 11px 15px; font-size: 11px; font-weight: 600; }
            QPushButton:hover { color: #e8f7ff; background: #17283c; border-color: #39afd0; }
            QPushButton:disabled { color: #536174; border-color: #1a2636; }
            QPushButton#send { color: #06131d; background: #69dfff; border-color: #69dfff; }
            QPushButton#send:hover { background: #a1eeff; }
            QPushButton#voice { color: #9fe9d6; border-color: #276b60; }
            QPushButton#voice:hover { background: #14312e; border-color: #55c8aa; }
            QPushButton#stop-speech { color: #ffc49e; border-color: #744735; }
            QPushButton#close { color: #f1a38c; border-color: #51342f; }
            QPushButton#close:hover { background: #321f21; border-color: #e57d5f; }
        """)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(36, 24, 36, 22)
        layout.setSpacing(10)

        brand = QLabel("PASSAT")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline = QLabel("PERSONALNY ASYSTENT SAMOCHODOWY")
        tagline.setObjectName("tagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)
        layout.addWidget(tagline)

        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.core = CoreWidget()
        self.core.setMinimumHeight(250)
        self.core.setMaximumHeight(330)
        self.core.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.core, 1)

        hint = QLabel("TRYB TESTOWY  ·  WYBIERZ STAN INTERFEJSU")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self.status_buttons: list[QPushButton] = []
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for status in self.STATUSES:
            button = QPushButton(status)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, value=status: self.set_status(value))
            self.status_buttons.append(button)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        voice_controls = QHBoxLayout()
        self.microphone_button = QPushButton("ROZPOCZNIJ MÓWIENIE")
        self.microphone_button.setObjectName("voice")
        self.microphone_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.microphone_button.clicked.connect(self.toggle_recording)
        voice_controls.addWidget(self.microphone_button)

        self.stop_speech_button = QPushButton("PRZERWIJ MÓWIENIE")
        self.stop_speech_button.setObjectName("stop-speech")
        self.stop_speech_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_speech_button.setEnabled(False)
        self.stop_speech_button.clicked.connect(self.stop_speaking)
        voice_controls.addWidget(self.stop_speech_button)
        layout.addLayout(voice_controls)

        self.wake_word_button = QPushButton()
        self.wake_word_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wake_word_button.clicked.connect(self.toggle_wake_word)
        layout.addWidget(self.wake_word_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._update_wake_word_button()

        self.chat = QPlainTextEdit()
        self.chat.setObjectName("chat")
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Tutaj pojawi się rozmowa z Passatem.")
        self.chat.setMinimumHeight(120)
        self.chat.setMaximumHeight(220)
        layout.addWidget(self.chat)

        input_row = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setObjectName("message")
        self.message_input.setPlaceholderText("Napisz wiadomość…")
        self.message_input.returnPressed.connect(self.send_message)
        input_row.addWidget(self.message_input, 1)

        self.send_button = QPushButton("WYŚLIJ")
        self.send_button.setObjectName("send")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self.provider_label = QLabel()
        self.provider_label.setObjectName("provider")
        self.provider_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.provider_label)

        close_button = QPushButton("ZAMKNIJ PASSATA")
        close_button.setObjectName("close")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        if self.assistant.is_offline:
            self.set_status("OFFLINE")
            self.provider_label.setText("Dostawca: OFFLINE · odpowiedzi podstawowe")
        else:
            self.set_status("GOTOWY")
            self.provider_label.setText(
                f"{self.assistant.provider_name} skonfigurowano · połączenie zostanie "
                "sprawdzone przy pierwszej wiadomości"
            )
        if self.assistant.startup_notice:
            self.chat.appendPlainText(f"PASSAT: {self.assistant.startup_notice}")
        if self._wake_enabled:
            self._start_wake_word_listener()

    def set_status(self, status: str) -> None:
        """Aktualizuje etykietę statusu i barwy animowanego rdzenia."""
        colors = {
            "GOTOWY": ("#69dfff", "#ff9a57"),
            "SŁUCHAM": ("#42e6ff", "#78f5d0"),
            "MYŚLĘ": ("#8c9cff", "#54ddff"),
            "MÓWIĘ": ("#ff9a57", "#d95e52"),
            "OFFLINE": ("#ffd166", "#ff8c42"),
        }
        primary, secondary = colors[status]
        self.status_label.setText(f"●  {status}")
        self.status_label.setStyleSheet(
            f"color: {primary}; background: #102033; border: 1px solid {primary}; "
            "border-radius: 14px; padding: 9px 18px; font-size: 13px; "
            "font-weight: 700; letter-spacing: 3px;"
        )
        self.core.set_status(status, primary, secondary)

    @Slot()
    def send_message(self) -> None:
        """Dodaje wpis raz i zleca odpowiedź w puli wątków."""
        if self._sending or self._recording or self._speaking or self._shutdown_waiting:
            return
        message = self.message_input.text().strip()
        if not message:
            return

        self._stop_wake_word_listener()

        self._sending = True
        self.chat.appendPlainText(f"TY: {message}")
        self.message_input.clear()
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        for button in self.status_buttons:
            button.setEnabled(False)
        self.microphone_button.setEnabled(False)
        self.set_status("MYŚLĘ")

        worker = ReplyWorker(self.assistant, message)
        worker.signals.completed.connect(self._on_reply)
        worker.signals.failed.connect(self._on_worker_error)
        self._active_worker = worker
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_reply(self, reply: AssistantReply) -> None:
        self.chat.appendPlainText(f"PASSAT ({reply.provider_name}): {reply.text}")
        if reply.warning:
            self.chat.appendPlainText(f"INFORMACJA: {reply.warning}")

        self._reply_is_offline = reply.is_offline
        if reply.is_offline:
            self.provider_label.setText("Dostawca: OFFLINE · odpowiedzi podstawowe")
        else:
            self.provider_label.setText(
                f"{self.assistant.provider_name} · ostatnie żądanie zakończone powodzeniem"
            )
        self._pending_speech_text = prepare_tts_text(reply.text)
        self._start_pending_speech_when_ready()

    @Slot()
    def _on_worker_error(self) -> None:
        self.chat.appendPlainText(
            "PASSAT: Wystąpił nieoczekiwany błąd. Wiadomość nie została przetworzona."
        )
        self.provider_label.setText("Dostawca: OFFLINE · wystąpił błąd aplikacji")
        self.set_status("OFFLINE")
        self._finish_request()

    def _finish_request(self) -> None:
        self._sending = False
        self._active_worker = None
        self.message_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.microphone_button.setEnabled(True)
        self.microphone_button.setText("ROZPOCZNIJ MÓWIENIE")
        self.stop_speech_button.setEnabled(False)
        for button in self.status_buttons:
            button.setEnabled(True)
        self.message_input.setFocus()
        self._start_wake_word_listener()

    @Slot()
    def toggle_recording(self) -> None:
        """Rozpoczyna nagrywanie albo zatrzymuje bieżącą wypowiedź."""
        if self._recording:
            self.stop_recording()
        elif not self._sending and not self._speaking and not self._shutdown_waiting:
            self.start_recording()

    def start_recording(self) -> None:
        if self._wake_word_worker is not None:
            if self._recording or self._sending or self._speaking:
                return
            self._wake_manual_record_event.set()
            self._prepare_recording_ui()
            return
        if self._voice_input_worker is not None:
            return
        self._recording = True
        self._voice_stop_event = threading.Event()
        self._prepare_recording_ui()

        worker = VoiceInputWorker(self.voice_input_service, self._voice_stop_event)
        worker.signals.transcribed.connect(self._on_transcription)
        worker.signals.failed.connect(self._on_voice_input_error)
        worker.signals.finished.connect(self._on_voice_input_finished)
        self._voice_input_worker = worker
        self._thread_pool.start(worker)

    def _prepare_recording_ui(self) -> None:
        self._recording = True
        self.microphone_button.setText("ZATRZYMAJ NAGRYWANIE")
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.microphone_button.setEnabled(True)
        self.stop_speech_button.setEnabled(False)
        for button in self.status_buttons:
            button.setEnabled(False)
        self.set_status("SŁUCHAM")

    @Slot()
    def stop_recording(self) -> None:
        if self._voice_stop_event is not None:
            self._voice_stop_event.set()
        self._recording = False
        self.microphone_button.setEnabled(False)

    @Slot(str)
    def _on_transcription(self, transcript: str) -> None:
        if self._shutdown_waiting:
            return
        self._recording = False
        self.message_input.setText(transcript)
        self.send_message()

    @Slot(str)
    def _on_wake_transcription(self, transcript: str) -> None:
        if self._shutdown_waiting:
            return
        self._recording = False
        self.chat.appendPlainText(f"TY: {transcript}")
        self.message_input.setText(transcript)
        self.send_message()

    @Slot()
    def _on_wake_activated(self) -> None:
        if not self._shutdown_waiting:
            self.chat.appendPlainText("PASSAT: Hasło aktywacyjne rozpoznane.")

    @Slot()
    def _on_wake_recording_started(self) -> None:
        if self._shutdown_waiting:
            return
        if self._voice_stop_event is None:
            self._voice_stop_event = threading.Event()
        self._prepare_recording_ui()

    @Slot(str)
    def _on_wake_word_error(self, message: str) -> None:
        self._wake_enabled = False
        self._update_wake_word_button()
        if not self._shutdown_waiting:
            self.chat.appendPlainText(
                f"INFORMACJA: Nasłuch hasła wyłączony: {message} "
                "Nadal możesz używać przycisku mikrofonu i czatu."
            )

    @Slot()
    def _on_wake_word_finished(self) -> None:
        self._wake_word_worker = None
        self._wake_shutdown_event = None
        self._wake_manual_record_event = None
        self._voice_stop_event = None
        if self._sending or self._speaking or self._shutdown_waiting:
            self._start_pending_speech_when_ready()
            return
        self._recording = False
        self.microphone_button.setText("ROZPOCZNIJ MÓWIENIE")
        self.microphone_button.setEnabled(True)
        self.message_input.setEnabled(True)
        self.send_button.setEnabled(True)
        for button in self.status_buttons:
            button.setEnabled(True)
        self._start_pending_speech_when_ready()
        if not self._wake_enabled:
            self.set_status("OFFLINE" if self.assistant.is_offline else "GOTOWY")
        self._start_wake_word_listener()

    def toggle_wake_word(self) -> None:
        """Włącza lub wyłącza lokalne oczekiwanie na hasło Passat."""
        if self._wake_enabled:
            if self._recording:
                return
            self._wake_enabled = False
            self._stop_wake_word_listener()
            if self._wake_word_worker is not None:
                self.microphone_button.setEnabled(False)
            self.wake_word_button.setText("WŁĄCZ NASŁUCH HASŁA")
        else:
            self._wake_enabled = True
            self._update_wake_word_button()
            self._start_wake_word_listener()

    def _update_wake_word_button(self) -> None:
        self.wake_word_button.setText(
            "WYŁĄCZ NASŁUCH HASŁA" if self._wake_enabled else "WŁĄCZ NASŁUCH HASŁA"
        )

    def _start_wake_word_listener(self) -> None:
        if (
            not self._wake_enabled
            or self._wake_word_worker is not None
            or self._voice_input_worker is not None
            or self._sending
            or self._recording
            or self._speaking
            or self._shutdown_waiting
        ):
            return
        self._wake_shutdown_event = threading.Event()
        self._wake_manual_record_event = threading.Event()
        self._voice_stop_event = threading.Event()
        worker = WakeWordWorker(
            self.voice_input_service,
            self.settings.wake_word_model_path,
            self._wake_shutdown_event,
            self._wake_manual_record_event,
            self._voice_stop_event,
            engine=self._wake_engine,
        )
        worker.signals.engine_ready.connect(self._on_wake_engine_ready)
        worker.signals.activated.connect(self._on_wake_activated)
        worker.signals.recording_started.connect(self._on_wake_recording_started)
        worker.signals.transcribed.connect(self._on_wake_transcription)
        worker.signals.failed.connect(self._on_wake_word_error)
        worker.signals.finished.connect(self._on_wake_word_finished)
        self._wake_word_worker = worker
        self.microphone_button.setText("NAGRAJ RĘCZNIE")
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_wake_engine_ready(self, engine: object) -> None:
        self._wake_engine = engine

    def _stop_wake_word_listener(self) -> None:
        if self._wake_shutdown_event is not None:
            self._wake_shutdown_event.set()

    def _start_pending_speech_when_ready(self) -> None:
        if self._pending_speech_text is None or self._wake_word_worker is not None:
            return
        text = self._pending_speech_text
        self._pending_speech_text = None
        if not text:
            self.set_status("OFFLINE" if self._reply_is_offline else "GOTOWY")
            self._finish_request()
            return
        self._start_speaking(text)

    @Slot(str)
    def _on_voice_input_error(self, message: str) -> None:
        self.chat.appendPlainText(f"INFORMACJA: {message}")

    @Slot()
    def _on_voice_input_finished(self) -> None:
        self._recording = False
        self._voice_input_worker = None
        self._voice_stop_event = None
        if self._sending or self._shutdown_waiting:
            return
        self.microphone_button.setText("ROZPOCZNIJ MÓWIENIE")
        self.microphone_button.setEnabled(True)
        self.message_input.setEnabled(True)
        self.send_button.setEnabled(True)
        for button in self.status_buttons:
            button.setEnabled(True)
        self.set_status("OFFLINE" if self.assistant.is_offline else "GOTOWY")
        self._start_wake_word_listener()

    def _start_speaking(self, text: str) -> None:
        self._speaking = True
        self._speech_stop_event = threading.Event()
        self.stop_speech_button.setEnabled(True)
        self.microphone_button.setEnabled(False)
        for button in self.status_buttons:
            button.setEnabled(False)
        worker = SpeechOutputWorker(
            self.speech_output_service,
            text,
            self._speech_stop_event,
        )
        worker.signals.started.connect(self._on_speech_started)
        worker.signals.audio_level.connect(self.core.set_audio_level)
        worker.signals.failed.connect(self._on_speech_error)
        worker.signals.completed.connect(self._on_speech_finished)
        self._speech_output_worker = worker
        self._thread_pool.start(worker)

    @Slot()
    def _on_speech_started(self) -> None:
        if not self._shutdown_waiting:
            self.set_status("MÓWIĘ")

    @Slot(str)
    def _on_speech_error(self, message: str) -> None:
        self.chat.appendPlainText(f"INFORMACJA: {message} Odpowiedź tekstowa pozostaje dostępna.")

    @Slot(bool)
    def _on_speech_finished(self, interrupted: bool) -> None:
        del interrupted
        self._speaking = False
        self._speech_output_worker = None
        self._speech_stop_event = None
        self.core.set_audio_level(0.0)
        self.set_status("OFFLINE" if self._reply_is_offline else "GOTOWY")
        self._finish_request()

    @Slot()
    def stop_speaking(self) -> None:
        if self._speech_stop_event is not None:
            self._speech_stop_event.set()

    def closeEvent(self, event) -> None:
        """Kończy audio i czeka asynchronicznie na aktywne zadania robocze."""
        self._shutdown_waiting = True
        if self._voice_stop_event is not None:
            self._voice_stop_event.set()
        self._stop_wake_word_listener()
        if self._speech_stop_event is not None:
            self._speech_stop_event.set()
        if self._thread_pool.activeThreadCount() > 0:
            event.ignore()
            self.setWindowTitle("PASSAT — zamykanie…")
            self.setEnabled(False)
            QTimer.singleShot(100, self.close)
            return
        self.core.stop_animation()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Passat")
    window = PassatWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
