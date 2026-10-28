"""Nagrywanie krótkiej wypowiedzi i lokalna transkrypcja po polsku."""

from __future__ import annotations

import queue
import threading
from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class SpeechInputError(Exception):
    """Czytelny błąd wejścia głosowego, bez surowych danych urządzenia."""


class _VoiceActivityDetector:
    """Lekki detektor energii mowy z krótkim buforem początku wypowiedzi."""

    def __init__(
        self,
        sample_rate: int,
        silence_seconds: float,
        rms_threshold: float,
        pre_roll_ms: int,
        frame_samples: int,
    ):
        self.sample_rate = sample_rate
        self.silence_samples_limit = max(1, int(sample_rate * silence_seconds))
        self.rms_threshold = rms_threshold
        self._noise_floor = min(rms_threshold / 4, 0.001)
        self.frame_samples = max(1, frame_samples)
        pre_roll_frames = max(0, round(pre_roll_ms / 1000 * sample_rate / self.frame_samples))
        self._pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
        self.speech_started = False
        self.silence_samples = 0

    def observe_background(self, frame: bytes, np) -> None:
        """Powoli dopasowuje próg do tła, gdy Passat tylko nasłuchuje hasła."""
        samples = np.frombuffer(frame, dtype=np.int16)
        if not samples.size:
            return
        normalized = samples.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(normalized))))
        self._noise_floor = 0.98 * self._noise_floor + 0.02 * rms

    def _threshold(self) -> float:
        # Ograniczenie zapobiega nadmiernemu wzrostowi progu w głośnym otoczeniu.
        return max(self.rms_threshold, min(self._noise_floor * 2.5, 0.08))

    def prime(self, frame: bytes) -> None:
        """Dodaje ramkę aktywującą do bufora, bez uznawania jej za komendę."""
        self._pre_roll.append(frame)

    def process(self, frame: bytes, np) -> tuple[list[bytes], bool]:
        """Zwraca ramki do zachowania oraz informację o końcu wypowiedzi."""
        samples = np.frombuffer(frame, dtype=np.int16)
        if samples.size == 0:
            return [], False
        normalized = samples.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(normalized))))

        if not self.speech_started:
            self._pre_roll.append(frame)
            if rms < self._threshold():
                self._noise_floor = 0.98 * self._noise_floor + 0.02 * rms
                return [], False
            self.speech_started = True
            return list(self._pre_roll) or [frame], False

        if rms >= self._threshold():
            self.silence_samples = 0
        else:
            self.silence_samples += samples.size
        return [frame], self.silence_samples >= self.silence_samples_limit


class VoiceInputService:
    """Nagrywa z domyślnego mikrofonu i leniwie wczytuje faster-whisper."""

    SAMPLE_RATE = 16_000
    FRAME_SAMPLES = 1_600  # 100 ms audio, rozdzielczość licznika ciszy
    SILENCE_RMS_THRESHOLD = 0.004

    def __init__(
        self,
        model_name: str = "small",
        *,
        vad_silence_seconds: float = 0.8,
        vad_rms_threshold: float = SILENCE_RMS_THRESHOLD,
        vad_pre_roll_ms: int = 200,
    ):
        self.model_name = model_name
        self.vad_silence_seconds = max(0.1, vad_silence_seconds)
        self.vad_rms_threshold = max(0.0001, vad_rms_threshold)
        self.vad_pre_roll_ms = max(0, vad_pre_roll_ms)
        self._model = None

    def _new_vad(self, frame_samples: int) -> _VoiceActivityDetector:
        return _VoiceActivityDetector(
            self.SAMPLE_RATE,
            self.vad_silence_seconds,
            self.vad_rms_threshold,
            self.vad_pre_roll_ms,
            frame_samples,
        )

    def _collect_until_silence(self, audio_queue, stop_event, np, frame_samples: int):
        """Collects speech and its silence tail from an already-open input stream."""
        vad = self._new_vad(frame_samples)
        chunks: list[bytes] = []
        while True:
            try:
                frame = audio_queue.get(timeout=0.05)
            except queue.Empty:
                if stop_event.is_set():
                    break
                continue

            frames_to_keep, silence_finished = vad.process(frame, np)
            chunks.extend(frames_to_keep)
            if silence_finished or stop_event.is_set():
                break

        if not vad.speech_started or not chunks:
            raise SpeechInputError("Nie wykryłem mowy. Powiedz coś i spróbuj ponownie.")
        return np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768.0

    def record(self, stop_event: threading.Event) -> object:
        """Nagrywa do ciszy po mowie; przycisk może zatrzymać nagranie wcześniej."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as error:
            raise SpeechInputError(
                "Brakuje bibliotek audio. Zainstaluj zależności z requirements.txt."
            ) from error

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=16)
        callback_error: list[str] = []

        def capture(indata, frames, time_info, status) -> None:
            del frames, time_info
            if status and "overflow" in str(status).lower():
                callback_error.append("overflow")
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                callback_error.append("overflow")

        try:
            sd.query_devices(kind="input")
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=self.FRAME_SAMPLES,
                callback=capture,
            ):
                audio = self._collect_until_silence(
                    audio_queue, stop_event, np, self.FRAME_SAMPLES
                )
        except sd.PortAudioError as error:
            raise SpeechInputError(
                "Nie można otworzyć mikrofonu. Sprawdź, czy jest podłączony i czy "
                "Passat ma dostęp do mikrofonu w ustawieniach Windows."
            ) from error
        except SpeechInputError:
            raise
        except Exception as error:
            raise SpeechInputError("Wystąpił błąd podczas nagrywania z mikrofonu.") from error

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
        """Nasłuchuje lokalnie, a po aktywacji kończy nagranie po ciszy.

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
        recording = False
        frame_samples = self.FRAME_SAMPLES
        vad: _VoiceActivityDetector | None = None
        chunks: list[bytes] = []
        background_vad = self._new_vad(frame_samples)

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
                blocksize=frame_samples,
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
                        vad = self._new_vad(frame_samples)
                        vad._noise_floor = background_vad._noise_floor
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
                        # Ramka aktywująca zawiera zwykle końcówkę słowa „Passat”.
                        # VAD zaczyna od kolejnej ramki, ale nadal zachowuje ją jako pre-roll.
                        vad = self._new_vad(frame_samples)
                        vad._noise_floor = background_vad._noise_floor
                        vad.prime(frame)
                        continue
                    if not recording:
                        background_vad.observe_background(frame, np)
                    if recording:
                        assert vad is not None
                        frames_to_keep, silence_finished = vad.process(frame, np)
                        chunks.extend(frames_to_keep)
                        if silence_finished or stop_recording_event.is_set():
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
        if vad is None or not vad.speech_started or not chunks:
            raise SpeechInputError("Nie wykryłem mowy. Powiedz coś i spróbuj ponownie.")
        return np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768.0

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
