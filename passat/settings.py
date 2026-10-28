"""Odczyt ustawień Passata ze zmiennych środowiskowych i pliku .env."""

import os
import math
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_STT_MODEL = "small"
DEFAULT_PIPER_MODEL = "models/voices/pl_PL-gosia-medium.onnx"
DEFAULT_VAD_SILENCE_SECONDS = 0.8
DEFAULT_VAD_RMS_THRESHOLD = 0.004
DEFAULT_VAD_PRE_ROLL_MS = 200


def _float_setting(name: str, default: float, minimum: float, maximum: float) -> float:
    """Czyta i ogranicza wartość liczbową, aby błędny .env nie zatrzymał GUI."""
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    if not math.isfinite(value):
        return default
    return min(max(value, minimum), maximum)


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


@dataclass(frozen=True)
class Settings:
    provider: str = "groq"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: str = ""
    groq_model: str = DEFAULT_GROQ_MODEL
    stt_model: str = DEFAULT_STT_MODEL
    piper_model: str = DEFAULT_PIPER_MODEL
    wake_word_enabled: bool = True
    wake_word_model_path: str = "models/wake-word/vosk-model-small-pl-0.22"
    vad_silence_seconds: float = DEFAULT_VAD_SILENCE_SECONDS
    vad_rms_threshold: float = DEFAULT_VAD_RMS_THRESHOLD
    vad_pre_roll_ms: int = DEFAULT_VAD_PRE_ROLL_MS

    @classmethod
    def from_env(cls) -> "Settings":
        # Nie zastępuj wartości ustawionych w systemie zawartością pliku .env.
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            provider=os.getenv("PASSAT_PROVIDER", "groq").strip().lower() or "groq",
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("PASSAT_GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
            or DEFAULT_GEMINI_MODEL,
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=os.getenv("PASSAT_GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
            or DEFAULT_GROQ_MODEL,
            stt_model=os.getenv("PASSAT_STT_MODEL", DEFAULT_STT_MODEL).strip()
            or DEFAULT_STT_MODEL,
            piper_model=os.getenv("PASSAT_PIPER_MODEL", DEFAULT_PIPER_MODEL).strip()
            or DEFAULT_PIPER_MODEL,
            wake_word_enabled=os.getenv("PASSAT_WAKE_WORD_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            wake_word_model_path=os.getenv(
                "PASSAT_WAKE_WORD_MODEL_PATH",
                "models/wake-word/vosk-model-small-pl-0.22",
            ).strip()
            or "models/wake-word/vosk-model-small-pl-0.22",
            vad_silence_seconds=_float_setting(
                "PASSAT_VAD_SILENCE_SECONDS", DEFAULT_VAD_SILENCE_SECONDS, 0.2, 5.0
            ),
            vad_rms_threshold=_float_setting(
                "PASSAT_VAD_RMS_THRESHOLD", DEFAULT_VAD_RMS_THRESHOLD, 0.0001, 0.1
            ),
            vad_pre_roll_ms=_int_setting("PASSAT_VAD_PRE_ROLL_MS", DEFAULT_VAD_PRE_ROLL_MS, 0, 1000),
        )
