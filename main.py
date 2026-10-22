"""Punkt startowy Passata i widok rozmowy w PySide6."""

import sys

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
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
        self._thread_pool = QThreadPool(self)
        self._active_worker: ReplyWorker | None = None
        self._sending = False

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
        if self._sending:
            return
        message = self.message_input.text().strip()
        if not message:
            return

        self._sending = True
        self.chat.appendPlainText(f"TY: {message}")
        self.message_input.clear()
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        for button in self.status_buttons:
            button.setEnabled(False)
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

        if reply.is_offline:
            self.provider_label.setText("Dostawca: OFFLINE · odpowiedzi podstawowe")
            self.set_status("OFFLINE")
        else:
            self.provider_label.setText(
                f"{self.assistant.provider_name} · ostatnie żądanie zakończone powodzeniem"
            )
            self.set_status("GOTOWY")
        self._finish_request()

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
        for button in self.status_buttons:
            button.setEnabled(True)
        self.message_input.setFocus()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Passat")
    window = PassatWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
