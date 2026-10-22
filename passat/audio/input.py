"""Nagrywanie krótkiej wypowiedzi i lokalna transkrypcja po polsku."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class SpeechInputError(Exception):
    """Czytelny błąd wejścia głosowego, bez surowych danych urządzenia."""


class VoiceInputService:
    """Nagrywa z domyślnego mikrofonu i leniwie wczytuje faster-whisper."""

    SAMPLE_RATE = 16_000
    MAX_RECORDING_SECONDS = 90
    SILENCE_RMS_THRESHOLD = 0.004

    def __init__(self, model_name: str = "small"):
        self.model_name = model_name
        self._model = None

    def record(self, stop_event: threading.Event) -> object:
        """Nagrywa do zatrzymania przyciskiem; audio zostaje tylko w pamięci."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as error:
            raise SpeechInputError(
                "Brakuje bibliotek audio. Zainstaluj zależności z requirements.txt."
            ) from error

        chunks = []
        callback_error: list[str] = []

        def capture(indata, frames, time_info, status) -> None:
            del frames, time_info
            if status and "overflow" in str(status).lower():
                callback_error.append("overflow")
            chunks.append(indata.copy())

        try:
            sd.query_devices(kind="input")
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=capture,
            ):
                started_at = time.monotonic()
                while not stop_event.wait(0.1):
                    if time.monotonic() - started_at >= self.MAX_RECORDING_SECONDS:
                        break
        except sd.PortAudioError as error:
            raise SpeechInputError(
                "Nie można otworzyć mikrofonu. Sprawdź, czy jest podłączony i czy "
                "Passat ma dostęp do mikrofonu w ustawieniach Windows."
            ) from error
        except Exception as error:
            raise SpeechInputError("Wystąpił błąd podczas nagrywania z mikrofonu.") from error

        if not chunks:
            raise SpeechInputError("Nie zarejestrowano dźwięku. Spróbuj ponownie.")
        audio = np.concatenate(chunks, axis=0).reshape(-1).astype(np.float32, copy=False)
        if audio.size < self.SAMPLE_RATE // 4:
            raise SpeechInputError("Nagranie jest za krótkie. Powiedz coś jeszcze raz.")
        rms = float(np.sqrt(np.mean(np.square(audio))))
        if rms < self.SILENCE_RMS_THRESHOLD:
            raise SpeechInputError("Nie wykryłem mowy. Sprawdź mikrofon i spróbuj ponownie.")
        if callback_error:
            raise SpeechInputError("Nagranie zostało przerwane przez problem z buforem audio.")
        return audio

    def transcribe(self, audio: object) -> str:
        """Rozpoznaje polską wypowiedź; model ładuje się dopiero przy pierwszej próbie."""
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise SpeechInputError(
                "Brakuje faster-whisper. Zainstaluj zależności głosowe z requirements.txt."
            ) from error

        try:
            if self._model is None:
                self._model = WhisperModel(
                    self.model_name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    num_workers=1,
                )
            segments, _info = self._model.transcribe(
                audio,
                language="pl",
                beam_size=5,
                vad_filter=True,
            )
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as error:
            raise SpeechInputError(
                "Nie udało się rozpoznać wypowiedzi. Sprawdź dostępność modelu i spróbuj ponownie."
            ) from error

        if not transcript:
            raise SpeechInputError("Nie rozpoznałem słów. Spróbuj powiedzieć to jeszcze raz.")
        return transcript


class VoiceInputSignals(QObject):
    transcribed = Signal(str)
    failed = Signal(str)
    finished = Signal()


class VoiceInputWorker(QRunnable):
    """Nagrywa i rozpoznaje mowę poza wątkiem GUI."""

    def __init__(
        self,
        service: VoiceInputService,
        stop_event: threading.Event,
        *,
        record: Callable[[threading.Event], object] | None = None,
        transcribe: Callable[[object], str] | None = None,
    ):
        super().__init__()
        self.service = service
        self.stop_event = stop_event
        self._record = record or service.record
        self._transcribe = transcribe or service.transcribe
        self.signals = VoiceInputSignals()

    @Slot()
    def run(self) -> None:
        try:
            audio = self._record(self.stop_event)
            transcript = self._transcribe(audio)
            if transcript.strip():
                self.signals.transcribed.emit(transcript.strip())
            else:
                self.signals.failed.emit("Nie rozpoznałem słów. Spróbuj powiedzieć to jeszcze raz.")
        except SpeechInputError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            self.signals.failed.emit("Wystąpił nieoczekiwany błąd rozpoznawania mowy.")
        finally:
            self.signals.finished.emit()
