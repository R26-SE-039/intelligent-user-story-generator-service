"""Configuration for speech-to-text capabilities."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.config import Settings


@dataclass(frozen=True)
class SpeechServiceSettings:
    """Runtime settings for speech/meeting features."""

    transcription_timeout_seconds: int
    polling_interval_seconds: float
    cors_origins: list[str]
    auth_secret: str
    azure_speech_key: str
    azure_speech_region: str


def load_speech_settings() -> SpeechServiceSettings:
    """Load speech settings from the unified Settings object."""
    s = Settings()
    return SpeechServiceSettings(
        transcription_timeout_seconds=int(
            getattr(s, "transcription_timeout_seconds", 120)
        ),
        polling_interval_seconds=float(
            getattr(s, "transcription_poll_interval_seconds", 1.2)
        ),
        cors_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5175",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        auth_secret=s.auth_secret.strip(),
        azure_speech_key=s.azure_speech_key.strip(),
        azure_speech_region=s.azure_speech_region.strip(),
    )
