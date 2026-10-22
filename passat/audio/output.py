"""Lokalna synteza Piper i odtwarzanie z pomiarem głośności audio."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class SpeechOutputError(Exception):
    """Czytelny błąd syntezy lub odtwarzania mowy."""


class PiperSpeechService:
    """Leniwie wczytuje lokalny głos Piper i odtwarza go porcjami."""

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        if not self.model_path.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            self.model_path = project_root / self.model_path
        self._voice = None

    def speak(
        self,
        text: str,
        stop_event: threading.Event,
        on_started: Callable[[], None],
        on_audio_level: Callable[[float], None],
    ) -> bool:
        """Odtwarza tekst; zwraca True, jeśli odtwarzanie przerwano."""
        if not self.model_path.is_file() or not Path(f"{self.model_path}.json").is_file():
            raise SpeechOutputError(
                "Nie znaleziono głosu Piper. Pobierz pliki .onnx i .onnx.json; instrukcja jest w README."
            )
        try:
            import numpy as np
            import sounddevice as sd
            from piper import PiperVoice
        except ImportError as error:
            raise SpeechOutputError(
                "Brakuje Piper lub bibliotek audio. Zainstaluj zależności z requirements.txt."
            ) from error

        stream = None
        try:
            if self._voice is None:
                self._voice = PiperVoice.load(self.model_path)

            started = False
            for audio_chunk in self._voice.synthesize(text):
                if stop_event.is_set():
                    break
                samples = np.frombuffer(audio_chunk.audio_int16_bytes, dtype=np.int16)
                channels = audio_chunk.sample_channels
                if channels > 1:
                    samples = samples.reshape(-1, channels)
                else:
                    samples = samples.reshape(-1, 1)
                if stream is None:
                    stream = sd.OutputStream(
                        samplerate=audio_chunk.sample_rate,
                        channels=channels,
                        dtype="int16",
                    )
                    stream.start()

                frames_per_block = max(1, audio_chunk.sample_rate // 20)
                for start in range(0, len(samples), frames_per_block):
                    if stop_event.is_set():
                        break
                    block = samples[start : start + frames_per_block]
                    if not started:
                        on_started()
                        started = True
                    stream.write(block.copy())
                    rms = float(np.sqrt(np.mean(np.square(block.astype(np.float32) / 32768.0))))
                    on_audio_level(min(1.0, rms * 3.0))
                if stop_event.is_set():
                    break

            on_audio_level(0.0)
            return stop_event.is_set()
        except SpeechOutputError:
            raise
        except Exception as error:
            raise SpeechOutputError(
                "Nie udało się wygenerować lub odtworzyć głosu Passata."
            ) from error
        finally:
            if stream is not None:
                try:
                    stream.stop()
                finally:
                    stream.close()


class SpeechOutputSignals(QObject):
    started = Signal()
    audio_level = Signal(float)
    failed = Signal(str)
    completed = Signal(bool)


class SpeechOutputWorker(QRunnable):
    """Syntezuje i odtwarza odpowiedź poza wątkiem GUI."""

    def __init__(
        self,
        service: PiperSpeechService,
        text: str,
        stop_event: threading.Event,
        *,
        speak: Callable[..., bool] | None = None,
    ):
        super().__init__()
        self.service = service
        self.text = text
        self.stop_event = stop_event
        self._speak = speak or service.speak
        self.signals = SpeechOutputSignals()

    @Slot()
    def run(self) -> None:
        try:
            interrupted = self._speak(
                self.text,
                self.stop_event,
                self.signals.started.emit,
                self.signals.audio_level.emit,
            )
        except SpeechOutputError as error:
            self.signals.failed.emit(str(error))
            interrupted = False
        except Exception:
            self.signals.failed.emit("Wystąpił nieoczekiwany błąd syntezy mowy.")
            interrupted = False
        finally:
            self.signals.completed.emit(locals().get("interrupted", False))
