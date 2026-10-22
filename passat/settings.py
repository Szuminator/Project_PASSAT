"""Odczyt ustawień Passata ze zmiennych środowiskowych i pliku .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_STT_MODEL = "small"
DEFAULT_PIPER_MODEL = "models/voices/pl_PL-gosia-medium.onnx"


@dataclass(frozen=True)
class Settings:
    provider: str = "groq"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: str = ""
    groq_model: str = DEFAULT_GROQ_MODEL
    stt_model: str = DEFAULT_STT_MODEL
    piper_model: str = DEFAULT_PIPER_MODEL

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
        )
