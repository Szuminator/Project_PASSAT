"""Nagrywanie krótkiej wypowiedzi i lokalna transkrypcja po polsku."""

from __future__ import annotations

import threading
import queue
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class SpeechInputError(Exception):
    """Czytelny błąd wejścia głosowego, bez surowych danych urządzenia."""


class VoiceInputService:
    """Nagrywa z domyślnego mikrofonu i leniwie wczytuje faster-whisper."""

    SAMPLE_RATE = 16_000
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
                while not stop_event.wait(0.1):
                    pass
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

    def listen_for_wake_word_and_record(
        self,
        detector,
        shutdown_event: threading.Event,
        manual_record_event: threading.Event,
        stop_recording_event: threading.Event,
        on_activated: Callable[[], None],
        on_recording_started: Callable[[], None],
    ) -> object | None:
        """Nasłuchuje lokalnie, a po aktywacji nagrywa do ręcznego zatrzymania.

        Jedno wejście audio obsługuje zarówno detekcję, jak i nagranie. Dzięki temu
        mikrofon nie jest otwierany przez dwa niezależne procesy.
        """
        if shutdown_event.is_set():
            return None
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as error:
            raise SpeechInputError(
                "Brakuje bibliotek audio. Zainstaluj zależności z requirements.txt."
            ) from error

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=8)
        callback_errors: list[str] = []
        chunks: list[bytes] = []
        recording = False

        def capture(indata, frames, time_info, status) -> None:
            del frames, time_info
            if status:
                callback_errors.append(str(status))
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                callback_errors.append("overflow")

        try:
            sd.query_devices(kind="input")
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=4_000,
                callback=capture,
            ):
                while not shutdown_event.is_set():
                    if callback_errors:
                        raise SpeechInputError(
                            "Nasłuch przerwano przez problem z buforem mikrofonu."
                        )
                    if not recording and manual_record_event.is_set():
                        manual_record_event.clear()
                        recording = True
                        on_recording_started()

                    try:
                        frame = audio_queue.get(timeout=0.05)
                    except queue.Empty:
                        if recording and stop_recording_event.is_set():
                            break
                        continue

                    if not recording and detector.detect(frame):
                        recording = True
                        on_activated()
                        on_recording_started()
                    if recording:
                        chunks.append(frame)
                        if stop_recording_event.is_set():
                            break
        except sd.PortAudioError as error:
            raise SpeechInputError(
                "Nie można otworzyć mikrofonu. Sprawdź, czy jest podłączony i czy "
                "Passat ma dostęp do mikrofonu w ustawieniach Windows."
            ) from error
        except SpeechInputError:
            raise
        except Exception as error:
            raise SpeechInputError(
                "Wystąpił błąd podczas lokalnego nasłuchu hasła lub nagrywania."
            ) from error

        if shutdown_event.is_set() and not recording:
            return None
        if callback_errors:
            raise SpeechInputError(
                "Nagranie zostało przerwane przez problem z buforem audio."
            )
        if not chunks:
            raise SpeechInputError("Nie zarejestrowano dźwięku. Spróbuj ponownie.")

        audio = np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size < self.SAMPLE_RATE // 4:
            raise SpeechInputError("Nagranie jest za krótkie. Powiedz coś jeszcze raz.")
        rms = float(np.sqrt(np.mean(np.square(audio))))
        if rms < self.SILENCE_RMS_THRESHOLD:
            raise SpeechInputError("Nie wykryłem mowy. Sprawdź mikrofon i spróbuj ponownie.")
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
