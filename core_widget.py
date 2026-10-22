"""Programowo rysowany, animowany rdzeń interfejsu Passat."""

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class CoreWidget(QWidget):
    """Własny widżet Qt z pulsującym rdzeniem i obracającymi się pierścieniami."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._primary = QColor("#69dfff")
        self._secondary = QColor("#ff9a57")
        self.setMinimumSize(300, 300)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def set_status(self, status: str, primary: str, secondary: str) -> None:
        """Zmienia barwy rdzenia zależnie od stanu asystenta."""
        self._primary = QColor(primary)
        self._secondary = QColor(secondary)
        self.update()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.025) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        cx, cy = float(center.x()), float(center.y())
        radius = min(self.width(), self.height()) * 0.34
        pulse = 1.0 + 0.035 * math.sin(self._phase * 1.5)

        # Miękka poświata za rdzeniem.
        glow = QRadialGradient(cx, cy, radius * 1.55)
        glow.setColorAt(0.0, QColor(self._primary.red(), self._primary.green(), self._primary.blue(), 36))
        glow.setColorAt(0.55, QColor(self._secondary.red(), self._secondary.green(), self._secondary.blue(), 12))
        glow.setColorAt(1.0, QColor(8, 13, 22, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, int(radius * 1.55), int(radius * 1.55))

        # Trzy cienkie, pulsujące orbity z ruchomymi punktami.
        for index, factor in enumerate((0.74, 1.0, 1.27)):
            ring_radius = radius * factor * pulse
            color = self._primary if index != 1 else self._secondary
            color = QColor(color)
            color.setAlpha(105 if index == 1 else 70)
            pen = QPen(color, 1.4 if index == 1 else 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, int(ring_radius), int(ring_radius))

            angle = self._phase * (1.0 if index % 2 == 0 else -0.72) + index * 1.9
            dot_x = cx + math.cos(angle) * ring_radius
            dot_y = cy + math.sin(angle) * ring_radius
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(int(dot_x - 3), int(dot_y - 3), 6, 6)

        # Wewnętrzna kula z gradientem niebiesko-pomarańczowym.
        core_radius = radius * 0.43 * pulse
        sphere = QRadialGradient(cx - core_radius * 0.28, cy - core_radius * 0.38, core_radius * 1.7)
        sphere.setColorAt(0.0, QColor("#effcff"))
        sphere.setColorAt(0.22, self._primary.lighter(145))
        sphere.setColorAt(0.66, self._primary)
        sphere.setColorAt(1.0, self._secondary.darker(135))
        painter.setPen(QPen(QColor(190, 243, 255, 180), 1.2))
        painter.setBrush(sphere)
        painter.drawEllipse(center, int(core_radius), int(core_radius))

        # Mały ciepły blik podkreśla pomarańczową część rdzenia.
        accent = QColor(self._secondary)
        accent.setAlpha(150)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawEllipse(int(cx + core_radius * 0.28), int(cy + core_radius * 0.15), 7, 7)
