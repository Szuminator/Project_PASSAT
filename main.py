"""Punkt startowy aplikacji Passat."""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt

from core_widget import CoreWidget


class PassatWindow(QMainWindow):
    """Główne okno i testowe sterowanie stanem interfejsu."""

    STATUSES = ("GOTOWY", "SŁUCHAM", "MYŚLĘ", "MÓWIĘ", "OFFLINE")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PASSAT — osobisty asystent jazdy")
        self.resize(920, 700)
        self.setMinimumSize(700, 620)
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #080d16; color: #e8f2ff; }
            QLabel#brand { color: #eaf5ff; font-size: 28px; font-weight: 700; letter-spacing: 12px; }
            QLabel#tagline { color: #72839d; font-size: 11px; letter-spacing: 3px; }
            QLabel#status { color: #69dfff; font-size: 13px; font-weight: 700; letter-spacing: 3px;
                            background: #102033; border: 1px solid #1d526a; border-radius: 14px;
                            padding: 9px 18px; }
            QLabel#hint { color: #687992; font-size: 11px; letter-spacing: 1px; }
            QPushButton { color: #b8c8dc; background: #101a29; border: 1px solid #203149;
                          border-radius: 10px; padding: 11px 15px; font-size: 11px; font-weight: 600; }
            QPushButton:hover { color: #e8f7ff; background: #17283c; border-color: #39afd0; }
            QPushButton#close { color: #f1a38c; border-color: #51342f; }
            QPushButton#close:hover { background: #321f21; border-color: #e57d5f; }
        """)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(44, 30, 44, 28)
        layout.setSpacing(12)

        brand = QLabel("PASSAT")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline = QLabel("PERSONALNY ASYSTENT SAMOCHODOWY")
        tagline.setObjectName("tagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)
        layout.addWidget(tagline)
        layout.addSpacing(12)

        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.core = CoreWidget()
        self.core.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.core, 1)

        hint = QLabel("TRYB TESTOWY  ·  WYBIERZ STAN INTERFEJSU")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        for status in self.STATUSES:
            button = QPushButton(status)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, value=status: self.set_status(value))
            buttons.addWidget(button)
        layout.addLayout(buttons)

        close_button = QPushButton("ZAMKNIJ PASSATA")
        close_button.setObjectName("close")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.set_status("GOTOWY")

    def set_status(self, status: str) -> None:
        """Aktualizuje opis i wygląd rdzenia dla wybranego stanu."""
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Passat")
    window = PassatWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
