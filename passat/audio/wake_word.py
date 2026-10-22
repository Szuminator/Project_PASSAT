"""Lokalna, wymienna warstwa wykrywania hasła aktywacyjnego Passata."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from passat.audio.input import SpeechInputError, VoiceInputService


class WakeWordError(Exception):
    """Czytelny błąd konfiguracji lub inicjalizacji lokalnego detektora."""


class VoskWakeWordEngine:
    """Wykrywa polskie słowo „Passat” przez lokalny model Vosk."""

    SAMPLE_RATE = 16_000

    def __init__(self, model_path: str | Path):
        path = Path(model_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        if not path.is_dir():
            raise WakeWordError(
                f"Nie znaleziono modelu hasła aktywacyjnego: {path}. "
                "Pobierz polski model Vosk zgodnie z instrukcją w README."
            )
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel

            SetLogLevel(-1)
            self._recognizer_factory = KaldiRecognizer
            self._model = Model(str(path))
            self._reset_recognizer()
        except ImportError as error:
            raise WakeWordError(
                "Brakuje biblioteki vosk. Zainstaluj zależności z requirements.txt."
            ) from error
        except Exception as error:
            raise WakeWordError(
                "Nie udało się załadować polskiego modelu Vosk do wykrywania hasła."
            ) from error

    def _reset_recognizer(self) -> None:
        """Tworzy czysty dekoder, zachowując już załadowany model w pamięci."""
        self._recognizer = self._recognizer_factory(
            self._model,
            self.SAMPLE_RATE,
            json.dumps(["passat", "[unk]"], ensure_ascii=False),
        )

    def reset(self) -> None:
        self._reset_recognizer()

    @staticmethod
    def _contains_wake_word(text: str) -> bool:
        words = re.findall(r"[\wąćęłńóśźż]+", text.casefold())
        return "passat" in words

    def detect(self, frame: bytes) -> bool:
        if self._recognizer.AcceptWaveform(frame):
            result = json.loads(self._recognizer.Result())
        else:
            result = json.loads(self._recognizer.PartialResult())
        return self._contains_wake_word(result.get("text", "") or result.get("partial", ""))


class WakeWordSignals(QObject):
    engine_ready = Signal(object)
    activated = Signal()
    recording_started = Signal()
    transcribed = Signal(str)
    failed = Signal(str)
    finished = Signal()


class WakeWordWorker(QRunnable):
    """Czuwa lokalnie, nagrywa po haśle i transkrybuje poza GUI."""

    def __init__(
        self,
        input_service: VoiceInputService,
        model_path: str | Path,
        shutdown_event: threading.Event,
        manual_record_event: threading.Event,
        stop_recording_event: threading.Event,
        *,
        engine_factory: Callable[[str | Path], object] = VoskWakeWordEngine,
        engine: object | None = None,
        session: Callable[..., object | None] | None = None,
        transcribe: Callable[[object], str] | None = None,
    ):
        super().__init__()
        self.input_service = input_service
        self.model_path = model_path
        self.shutdown_event = shutdown_event
        self.manual_record_event = manual_record_event
        self.stop_recording_event = stop_recording_event
        self._engine_factory = engine_factory
        self.engine = engine
        self._session = session or input_service.listen_for_wake_word_and_record
        self._transcribe = transcribe or input_service.transcribe
        self.signals = WakeWordSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.engine is None:
                engine = self._engine_factory(self.model_path)
                self.signals.engine_ready.emit(engine)
            else:
                engine = self.engine
                reset = getattr(engine, "reset", None)
                if callable(reset):
                    reset()
            audio = self._session(
                engine,
                self.shutdown_event,
                self.manual_record_event,
                self.stop_recording_event,
                self.signals.activated.emit,
                self.signals.recording_started.emit,
            )
            if audio is not None and not self.shutdown_event.is_set():
                transcript = self._transcribe(audio).strip()
                if transcript and not self.shutdown_event.is_set():
                    self.signals.transcribed.emit(transcript)
                elif not transcript and not self.shutdown_event.is_set():
                    self.signals.failed.emit(
                        "Nie rozpoznałem słów. Spróbuj powiedzieć to jeszcze raz."
                    )
        except WakeWordError as error:
            self.signals.failed.emit(str(error))
        except SpeechInputError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            self.signals.failed.emit(
                "Wystąpił nieoczekiwany błąd wykrywania hasła lub rozpoznawania mowy."
            )
        finally:
            self.signals.finished.emit()
