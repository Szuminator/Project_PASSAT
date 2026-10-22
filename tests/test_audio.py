import threading
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from core_widget import CoreWidget
from passat.audio.input import SpeechInputError, VoiceInputService, VoiceInputWorker
from passat.audio.output import (
    PiperSpeechService,
    SpeechOutputError,
    SpeechOutputWorker,
)


def run_voice_worker(worker):
    results = []
    errors = []
    finished = []
    worker.signals.transcribed.connect(results.append)
    worker.signals.failed.connect(errors.append)
    worker.signals.finished.connect(lambda: finished.append(True))
    worker.run()
    return results, errors, finished


def test_voice_worker_transcribes_once_and_finishes():
    stop_event = threading.Event()
    service = VoiceInputService()
    worker = VoiceInputWorker(
        service,
        stop_event,
        record=lambda _event: np.ones(100, dtype=np.float32),
        transcribe=lambda _audio: "  Jaka jest pogoda?  ",
    )

    results, errors, finished = run_voice_worker(worker)

    assert results == ["Jaka jest pogoda?"]
    assert errors == []
    assert finished == [True]


def test_voice_worker_reports_microphone_and_recognition_errors():
    worker = VoiceInputWorker(
        VoiceInputService(),
        threading.Event(),
        record=lambda _event: (_ for _ in ()).throw(SpeechInputError("Brak mikrofonu.")),
        transcribe=lambda _audio: pytest.fail("transcription should not run"),
    )

    results, errors, finished = run_voice_worker(worker)

    assert results == []
    assert errors == ["Brak mikrofonu."]
    assert finished == [True]


def test_voice_worker_handles_empty_transcript():
    worker = VoiceInputWorker(
        VoiceInputService(),
        threading.Event(),
        record=lambda _event: np.ones(100, dtype=np.float32),
        transcribe=lambda _audio: "  ",
    )

    results, errors, finished = run_voice_worker(worker)

    assert results == []
    assert "Nie rozpoznałem słów" in errors[0]
    assert finished == [True]


def test_recognizer_loads_small_int8_model_lazily_and_sets_polish(monkeypatch):
    calls = {}

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            calls["audio"] = audio
            calls["transcribe"] = kwargs
            return iter([SimpleNamespace(text=" Dzień dobry.")]), SimpleNamespace(language="pl")

    def make_model(name, **kwargs):
        calls["model"] = (name, kwargs)
        return FakeModel()

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=make_model))
    service = VoiceInputService("small")
    assert service._model is None

    audio = np.ones(100, dtype=np.float32)
    assert service.transcribe(audio) == "Dzień dobry."
    assert calls["model"] == (
        "small",
        {"device": "cpu", "compute_type": "int8", "cpu_threads": 4, "num_workers": 1},
    )
    assert calls["transcribe"] == {"language": "pl", "beam_size": 5, "vad_filter": True}


def test_recorder_reports_missing_or_denied_microphone(monkeypatch):
    class FakePortAudioError(Exception):
        pass

    def missing_device(*_args, **_kwargs):
        raise FakePortAudioError("device detail")

    fake_sounddevice = SimpleNamespace(
        PortAudioError=FakePortAudioError,
        query_devices=missing_device,
        InputStream=object,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    with pytest.raises(SpeechInputError, match="Nie można otworzyć mikrofonu"):
        VoiceInputService().record(threading.Event())


def test_piper_reports_missing_voice_without_loading_audio(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "piper", None)
    service = PiperSpeechService(tmp_path / "missing.onnx")

    with pytest.raises(SpeechOutputError, match="Nie znaleziono głosu Piper"):
        service.speak("Cześć", threading.Event(), lambda: None, lambda _level: None)


def test_piper_playback_reports_real_rms_level_and_closes_stream(monkeypatch, tmp_path):
    model_path = tmp_path / "voice.onnx"
    model_path.touch()
    model_path.with_suffix(".onnx.json").touch()
    chunk = SimpleNamespace(
        audio_int16_bytes=np.array([0, 4096, -4096, 8192, -8192], dtype=np.int16).tobytes(),
        sample_channels=1,
        sample_rate=100,
    )

    class FakeVoice:
        def synthesize(self, _text):
            yield chunk

    class FakePiperVoice:
        @staticmethod
        def load(_path):
            return FakeVoice()

    class FakeOutputStream:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.blocks = []
            self.closed = False

        def start(self):
            pass

        def write(self, block):
            self.blocks.append(block)

        def stop(self):
            pass

        def close(self):
            self.closed = True

    output_streams = []

    def make_stream(**kwargs):
        stream = FakeOutputStream(**kwargs)
        output_streams.append(stream)
        return stream

    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=FakePiperVoice))
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(OutputStream=make_stream))
    service = PiperSpeechService(model_path)
    levels = []
    started = []

    interrupted = service.speak("Test", threading.Event(), lambda: started.append(True), levels.append)

    assert interrupted is False
    assert started == [True]
    assert len(levels) == 2  # blok z RMS i końcowe wyzerowanie poziomu
    assert 0 < levels[0] < 1
    assert levels[-1] == 0
    assert output_streams[0].options["dtype"] == "int16"
    assert output_streams[0].closed


def test_speech_worker_handles_interruption_and_unavailable_engine():
    stop_event = threading.Event()

    def interrupted_speak(_text, _event, on_started, on_level):
        on_started()
        on_level(0.7)
        stop_event.set()
        return True

    worker = SpeechOutputWorker(
        PiperSpeechService("not-used"),
        "Odpowiedź",
        stop_event,
        speak=interrupted_speak,
    )
    started = []
    levels = []
    completed = []
    worker.signals.started.connect(lambda: started.append(True))
    worker.signals.audio_level.connect(levels.append)
    worker.signals.completed.connect(completed.append)
    worker.run()

    assert started == [True]
    assert levels == [0.7]
    assert completed == [True]

    failed_worker = SpeechOutputWorker(
        PiperSpeechService("not-used"),
        "Odpowiedź tekstowa",
        threading.Event(),
        speak=lambda *_args: (_ for _ in ()).throw(SpeechOutputError("Brak głosu.")),
    )
    errors = []
    failed_worker.signals.failed.connect(errors.append)
    failed_worker.run()
    assert errors == ["Brak głosu."]


def test_core_audio_level_is_clamped_and_smoothed(qapp):
    core = CoreWidget()
    core.set_status("MÓWIĘ", "#ff9a57", "#d95e52")
    core.set_audio_level(3.0)
    core._advance()

    assert core._audio_level == 1.0
    assert 0 < core._display_audio_level < 1.0

    core.set_audio_level(-1.0)
    assert core._audio_level == 0.0
    core.stop_animation()
