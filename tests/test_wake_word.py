import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from passat.audio.wake_word import VoskWakeWordEngine, WakeWordError, WakeWordWorker


def test_detector_matches_polish_wake_word_as_separate_word():
    assert VoskWakeWordEngine._contains_wake_word("passat")
    assert VoskWakeWordEngine._contains_wake_word("Słucham, PASSAT!")
    assert not VoskWakeWordEngine._contains_wake_word("passata")
    assert not VoskWakeWordEngine._contains_wake_word("kompasat")


def test_missing_model_fails_without_downloading(tmp_path):
    with pytest.raises(WakeWordError, match="Nie znaleziono modelu"):
        VoskWakeWordEngine(tmp_path / "missing-model")


def test_vosk_detector_reads_local_partial_result(tmp_path, monkeypatch):
    model_path = tmp_path / "model"
    model_path.mkdir()
    calls = {}

    class FakeRecognizer:
        def __init__(self, _model, sample_rate, grammar):
            calls["settings"] = (sample_rate, grammar)

        def AcceptWaveform(self, _frame):
            return False

        def PartialResult(self):
            return '{"partial": "Passat"}'

    monkeypatch.setitem(
        __import__("sys").modules,
        "vosk",
        SimpleNamespace(
            KaldiRecognizer=FakeRecognizer,
            Model=lambda path: path,
            SetLogLevel=lambda _level: None,
        ),
    )
    detector = VoskWakeWordEngine(model_path)

    assert detector.detect(b"local audio")
    assert calls["settings"][0] == 16_000
    assert '"passat"' in calls["settings"][1]


def test_wake_worker_orders_activation_recording_and_transcription():
    events = []
    shutdown = threading.Event()
    manual_record = threading.Event()
    stop_recording = threading.Event()

    def run_session(_engine, _shutdown, _manual, _stop, activated, recording_started):
        events.append("nasłuch")
        activated()
        recording_started()
        events.append("nagrywanie")
        return object()

    worker = WakeWordWorker(
        input_service=SimpleNamespace(transcribe=lambda _audio: ""),
        model_path=Path("not-loaded-by-mock"),
        shutdown_event=shutdown,
        manual_record_event=manual_record,
        stop_recording_event=stop_recording,
        engine_factory=lambda _path: object(),
        session=run_session,
        transcribe=lambda _audio: "Jaka jest godzina?",
    )
    worker.signals.activated.connect(lambda: events.append("hasło"))
    worker.signals.recording_started.connect(lambda: events.append("SŁUCHAM"))
    worker.signals.transcribed.connect(lambda _text: events.append("transkrypcja"))
    worker.signals.finished.connect(lambda: events.append("koniec"))

    worker.run()

    assert events == ["nasłuch", "hasło", "SŁUCHAM", "nagrywanie", "transkrypcja", "koniec"]


def test_wake_worker_reports_microphone_failure_and_always_finishes():
    events = []

    def broken_session(*_args):
        from passat.audio.input import SpeechInputError

        raise SpeechInputError("Mikrofon niedostępny.")

    worker = WakeWordWorker(
        input_service=SimpleNamespace(transcribe=lambda _audio: ""),
        model_path="unused",
        shutdown_event=threading.Event(),
        manual_record_event=threading.Event(),
        stop_recording_event=threading.Event(),
        engine_factory=lambda _path: object(),
        session=broken_session,
    )
    worker.signals.failed.connect(events.append)
    worker.signals.finished.connect(lambda: events.append("koniec"))

    worker.run()

    assert events == ["Mikrofon niedostępny.", "koniec"]


def test_wake_worker_discards_transcript_if_shutdown_arrives_during_stt():
    shutdown = threading.Event()
    events = []

    def transcribe(_audio):
        shutdown.set()
        return "Nie wysyłaj po zamknięciu"

    worker = WakeWordWorker(
        input_service=SimpleNamespace(transcribe=transcribe),
        model_path="unused",
        shutdown_event=shutdown,
        manual_record_event=threading.Event(),
        stop_recording_event=threading.Event(),
        engine_factory=lambda _path: object(),
        session=lambda *_args: object(),
    )
    worker.signals.transcribed.connect(events.append)
    worker.signals.finished.connect(lambda: events.append("koniec"))

    worker.run()

    assert events == ["koniec"]
