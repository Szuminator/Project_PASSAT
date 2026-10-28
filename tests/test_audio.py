import threading
import sys
import queue
from types import SimpleNamespace

import numpy as np
import pytest

from core_widget import CoreWidget
from passat.audio.input import (
    SpeechInputError,
    VoiceInputService,
    VoiceInputWorker,
    _VoiceActivityDetector,
)
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


def int16_frame(value, size=1_600):
    return np.full(size, value, dtype=np.int16).tobytes()


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


def test_recording_reports_missing_numpy_for_vad(monkeypatch):
    monkeypatch.setitem(sys.modules, "numpy", None)
    with pytest.raises(SpeechInputError, match="Brakuje bibliotek audio"):
        VoiceInputService().record(threading.Event())


def test_vad_waits_through_initial_silence_and_keeps_pre_roll():
    vad = _VoiceActivityDetector(16_000, 0.8, 0.004, 200, 1_600)

    for _ in range(5):
        assert vad.process(int16_frame(0), np) == ([], False)
    assert not vad.speech_started

    kept, finished = vad.process(int16_frame(1_500), np)

    assert vad.speech_started
    assert not finished
    assert len(kept) == 2
    assert kept[-1] == int16_frame(1_500)


def test_vad_ends_after_configured_silence_and_bridges_short_pause():
    vad = _VoiceActivityDetector(16_000, 0.8, 0.004, 200, 1_600)
    assert vad.process(int16_frame(2_000), np)[1] is False

    for _ in range(4):  # 0,4 s przerwy nie kończy zdania
        assert vad.process(int16_frame(0), np)[1] is False
    assert vad.process(int16_frame(2_000), np)[1] is False

    for _ in range(7):
        assert vad.process(int16_frame(0), np)[1] is False
    assert vad.process(int16_frame(0), np)[1] is True


def test_vad_accepts_very_short_and_long_utterances():
    short_vad = _VoiceActivityDetector(16_000, 0.2, 0.004, 100, 1_600)
    short_audio, _ = short_vad.process(int16_frame(2_000), np)
    assert short_vad.speech_started
    assert len(short_audio) == 1
    assert short_vad.process(int16_frame(0), np)[1] is False
    assert short_vad.process(int16_frame(0), np)[1] is True

    long_vad = _VoiceActivityDetector(16_000, 0.8, 0.004, 200, 1_600)
    for _ in range(100):
        _, finished = long_vad.process(int16_frame(2_000), np)
        assert not finished
    for _ in range(7):
        assert long_vad.process(int16_frame(0), np)[1] is False
    assert long_vad.process(int16_frame(0), np)[1] is True


def test_manual_stop_returns_audio_without_waiting_for_silence():
    service = VoiceInputService()
    audio_queue = queue.Queue()
    audio_queue.put(int16_frame(2_000))
    stop_event = threading.Event()
    stop_event.set()

    audio = service._collect_until_silence(audio_queue, stop_event, np, 1_600)

    assert audio.size == 1_600
    assert float(np.max(audio)) > 0


def test_manual_microphone_recording_also_ends_after_silence(monkeypatch):
    voice = np.full((1_600, 1), 2_000, dtype=np.int16)
    silence = np.zeros((1_600, 1), dtype=np.int16)
    stream_count = []

    class FakeStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
            stream_count.append(True)

        def __enter__(self):
            for frame in [silence, voice, voice] + [silence] * 9:
                self.callback(frame, len(frame), None, None)
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(
            PortAudioError=type("FakePortAudioError", (Exception,), {}),
            query_devices=lambda **_kwargs: None,
            InputStream=FakeStream,
        ),
    )

    audio = VoiceInputService().record(threading.Event())

    assert stream_count == [True]
    assert audio.size >= 1_600 * 9


def test_wake_listener_uses_one_stream_and_waits_for_manual_stop(monkeypatch):
    activated = threading.Event()
    recording_started = threading.Event()
    stop_recording = threading.Event()
    stream_count = []
    wake_frame = np.full((1_600, 1), 5_000, dtype=np.int16)
    voice_frame = np.full((1_600, 1), 6_000, dtype=np.int16)

    class FakeStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
            stream_count.append(True)

        def __enter__(self):
            self.callback(wake_frame, len(wake_frame), None, None)
            self.callback(voice_frame, len(voice_frame), None, None)
            return self

        def __exit__(self, *_args):
            return False

    fake_sounddevice = SimpleNamespace(
        PortAudioError=type("FakePortAudioError", (Exception,), {}),
        query_devices=lambda **_kwargs: None,
        InputStream=FakeStream,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    class Detector:
        def detect(self, _chunk):
            return True

    result = []
    errors = []

    def run_session():
        try:
            result.append(
                VoiceInputService().listen_for_wake_word_and_record(
                    Detector(),
                    threading.Event(),
                    threading.Event(),
                    stop_recording,
                    activated.set,
                    recording_started.set,
                )
            )
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=run_session)
    worker.start()
    assert activated.wait(timeout=1)
    assert recording_started.wait(timeout=1)
    # Brak ciszy nie kończy nagrania: nadal działa ta sama sesja mikrofonu.
    worker.join(timeout=0.2)
    assert worker.is_alive()
    assert len(stream_count) == 1

    stop_recording.set()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert errors == []
    assert result[0].shape == (3_200,)


def test_wake_listener_stops_after_silence_without_opening_second_stream(monkeypatch):
    wake = np.full((1_600, 1), 6_000, dtype=np.int16)
    speech = np.full((1_600, 1), 5_000, dtype=np.int16)
    silence = np.zeros((1_600, 1), dtype=np.int16)
    stream_count = []
    producer_threads = []

    class FakeStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
            stream_count.append(True)

        def __enter__(self):
            frames = [silence] * 3 + [wake, speech, speech] + [silence] * 9

            def produce():
                for frame in frames:
                    self.callback(frame, len(frame), None, None)
                    threading.Event().wait(0.003)

            thread = threading.Thread(target=produce)
            thread.start()
            producer_threads.append(thread)
            return self

        def __exit__(self, *_args):
            producer_threads[0].join(timeout=1)
            return False

    fake_sounddevice = SimpleNamespace(
        PortAudioError=type("FakePortAudioError", (Exception,), {}),
        query_devices=lambda **_kwargs: None,
        InputStream=FakeStream,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    class Detector:
        def detect(self, frame):
            return frame == wake.tobytes()

    activated = []
    recording_started = []
    audio = VoiceInputService().listen_for_wake_word_and_record(
        Detector(),
        threading.Event(),
        threading.Event(),
        threading.Event(),
        lambda: activated.append(True),
        lambda: recording_started.append(True),
    )

    assert len(stream_count) == 1
    assert activated == [True]
    assert recording_started == [True]
    assert audio.size >= 1_600 * 9


def test_wake_listener_reports_microphone_error(monkeypatch):
    class FakePortAudioError(Exception):
        pass

    def fail_query(**_kwargs):
        raise FakePortAudioError("no microphone")

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(
            PortAudioError=FakePortAudioError,
            query_devices=fail_query,
            InputStream=object,
        ),
    )
    with pytest.raises(SpeechInputError, match="Nie można otworzyć mikrofonu"):
        VoiceInputService().listen_for_wake_word_and_record(
            object(),
            threading.Event(),
            threading.Event(),
            threading.Event(),
            lambda: None,
            lambda: None,
        )


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
