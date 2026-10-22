"""Programowo rysowany, animowany rdzeń interfejsu Passat."""

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class CoreWidget(QWidget):
    """Własny widżet Qt z pulsującym rdzeniem i obracającymi się pierścieniami."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._status = "GOTOWY"
        self._audio_level = 0.0
        self._display_audio_level = 0.0
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
        self._status = status
        self._primary = QColor(primary)
        self._secondary = QColor(secondary)
        self.update()

    def set_audio_level(self, level: float) -> None:
        """Przyjmuje znormalizowany poziom odtwarzanego dźwięku z zakresu 0–1."""
        self._audio_level = max(0.0, min(1.0, float(level)))

    def stop_animation(self) -> None:
        """Zatrzymuje timer animacji podczas zamykania okna."""
        self._timer.stop()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.025) % (2 * math.pi)
        self._display_audio_level += (self._audio_level - self._display_audio_level) * 0.24
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        cx, cy = float(center.x()), float(center.y())
        radius = min(self.width(), self.height()) * 0.34
        speaking = self._status == "MÓWIĘ"
        pulse_amount = (0.06 + self._display_audio_level * 0.12) if speaking else 0.035
        pulse_speed = 2.4 if speaking else 1.5
        pulse = 1.0 + pulse_amount * math.sin(self._phase * pulse_speed)

        # Miękka poświata za rdzeniem.
        glow = QRadialGradient(cx, cy, radius * 1.55)
        glow.setColorAt(0.0, QColor(self._primary.red(), self._primary.green(), self._primary.blue(), 36))
        glow.setColorAt(0.55, QColor(self._secondary.red(), self._secondary.green(), self._secondary.blue(), 12))
        glow.setColorAt(1.0, QColor(8, 13, 22, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, int(radius * 1.55), int(radius * 1.55))

        # Trzy cienkie orbity. W stanie MÓWIĘ ich kształt faluje jak wizualizacja głosu.
        for index, factor in enumerate((0.74, 1.0, 1.27)):
            ring_radius = radius * factor * pulse
            color = self._primary if index != 1 else self._secondary
            color = QColor(color)
            color.setAlpha(105 if index == 1 else 70)
            pen = QPen(color, 1.4 if index == 1 else 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if speaking:
                path = QPainterPath()
                wave_size = radius * (0.025 + self._display_audio_level * 0.10)
                point_count = 240
                for point_index in range(point_count + 1):
                    angle_on_ring = 2 * math.pi * point_index / point_count
                    wave = wave_size * math.sin(
                        5 * angle_on_ring + self._phase * 3.2 + index * 1.1
                    )
                    point_radius = ring_radius + wave
                    x = cx + math.cos(angle_on_ring) * point_radius
                    y = cy + math.sin(angle_on_ring) * point_radius
                    if point_index == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                path.closeSubpath()
                painter.drawPath(path)
            else:
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
