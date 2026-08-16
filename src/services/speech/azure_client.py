"""Microsoft Azure Speech Service integration utilities."""

from __future__ import annotations

import azure.cognitiveservices.speech as speechsdk
from src.core.config import SpeechServiceSettings


class AzureSpeechClient:
    """Client for Azure Speech Service operations."""

    def __init__(self, settings: SpeechServiceSettings) -> None:
        self._settings = settings

    def get_speech_config(self) -> speechsdk.SpeechConfig:
        """Create and configure the Azure Speech SDK config."""
        if not self._settings.azure_speech_key or not self._settings.azure_speech_region:
            raise RuntimeError(
                "Azure Speech credentials (AZURE_SPEECH_KEY, AZURE_SPEECH_REGION) are not configured."
            )

        speech_config = speechsdk.SpeechConfig(
            subscription=self._settings.azure_speech_key,
            region=self._settings.azure_speech_region
        )
        speech_config.speech_recognition_language = "en-US"
        return speech_config

    def create_push_stream(
        self,
        samples_per_second: int = 16000,
        bits_per_sample: int = 16,
        channels: int = 1,
    ) -> speechsdk.audio.PushAudioInputStream:
        """Create a push stream configured for standard 16kHz 16-bit Mono PCM.

        The browser AudioWorklet automatically downsamples native hardware audio
        (48000 Hz or 44100 Hz) down to 16000 Hz before transmitting over WebSocket.
        Azure Speech SDK PushAudioInputStream requires 16000 Hz 16-bit Mono PCM format.

        Args:
            samples_per_second: 16000 (16kHz standard for Speech SDK).
            bits_per_sample: 16-bit PCM (Int16Array from browser worklet).
            channels: 1 (Mono).
        """
        stream_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=samples_per_second,
            bits_per_sample=bits_per_sample,
            channels=channels,
        )
        return speechsdk.audio.PushAudioInputStream(stream_format)
