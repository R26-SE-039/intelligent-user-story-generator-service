"""Azure Speech SDK continuous audio stream recognition service."""

from __future__ import annotations

import asyncio
import logging
import struct

import azure.cognitiveservices.speech as speechsdk
from src.services.speech.azure_client import AzureSpeechClient
from src.utils.helpers import utc_now

LOGGER = logging.getLogger(__name__)


class AzureStreamService:
    """Manages an active Azure Speech continuous recognition session over a push stream.

    Audio format contract:
      - The browser AudioContext runs at the hardware's native sample rate (48000 Hz).
      - The AudioWorklet converts Float32 → Int16 and streams raw PCM over WebSocket.
      - The push stream MUST be declared with the same rate (48000 Hz, 16-bit, Mono).
      - Azure Speech SDK natively supports 8000 / 16000 / 48000 Hz push streams.

    Threading note:
      - Azure SDK fires recognition callbacks on its own background thread.
      - We use `loop.call_soon_threadsafe` to safely enqueue results onto the
        asyncio event loop without any cross-thread races.
    """

    def __init__(self, azure_client: AzureSpeechClient) -> None:
        self.azure_client = azure_client
        self.push_stream: speechsdk.audio.PushAudioInputStream | None = None
        self.recognizer: speechsdk.SpeechRecognizer | None = None
        self._chunks_written: int = 0
        self._bytes_written: int = 0
        self._silent_chunks: int = 0

    def start(
        self,
        conn_id: str,
        speaker_label: str,
        meeting_id: str,
        loop: asyncio.AbstractEventLoop,
        result_queue: asyncio.Queue,
    ) -> bool:
        """Start continuous speech recognition for an active connection.

        Must be called from the asyncio thread. The recognizer is started in a
        thread-pool to avoid blocking the event loop during the Azure SDK handshake.
        """
        try:
            speech_config = self.azure_client.get_speech_config()
            speech_config.speech_recognition_language = "en-US"

            # Push stream: standard 16kHz 16-bit Mono PCM format.
            # The browser AudioWorklet downsamples native audio to 16kHz Int16 mono.
            self.push_stream = self.azure_client.create_push_stream(
                samples_per_second=16000,
                bits_per_sample=16,
                channels=1,
            )
            audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)

            self.recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
            )

            # ── Event callbacks (run on Azure SDK background thread) ──────────

            def handle_final_result(evt: speechsdk.SpeechRecognitionEventArgs) -> None:
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    text = evt.result.text.strip()
                    if not text:
                        return

                    LOGGER.info("[Azure] Final: %s → %r", speaker_label, text)

                    start_time = evt.result.offset / 10_000_000 if hasattr(evt.result, "offset") else None
                    duration   = evt.result.duration / 10_000_000 if hasattr(evt.result, "duration") else None
                    end_time   = (start_time + duration) if (start_time is not None and duration is not None) else None

                    payload = {
                        "type": "transcription",
                        "data": {
                            "text": text,
                            "speaker_id": conn_id,
                            "speaker_name": speaker_label,
                            "is_final": True,
                            "timestamp": utc_now(),
                            "timestamp_start": start_time,
                            "timestamp_end": end_time,
                        },
                    }
                    loop.call_soon_threadsafe(result_queue.put_nowait, payload)

                elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                    no_match_reason = getattr(evt.result.no_match_details, 'reason', 'unknown') if hasattr(evt.result, 'no_match_details') else 'unknown'
                    LOGGER.warning("[Azure] NoMatch for %s | reason=%s — audio may be silence or below recognition threshold", speaker_label, no_match_reason)
                else:
                    LOGGER.info("[Azure] Reason: %s for %s", evt.result.reason, speaker_label)

            def handle_partial_result(evt: speechsdk.SpeechRecognitionEventArgs) -> None:
                text = evt.result.text.strip()
                # Skip empty partials — they add noise to the queue and frontend.
                if not text:
                    return
                LOGGER.info("[Azure] Partial: %s → %r", speaker_label, text)
                payload = {
                    "type": "transcription",
                    "data": {
                        "text": text,
                        "speaker_id": conn_id,
                        "speaker_name": speaker_label,
                        "is_final": False,
                    },
                }
                loop.call_soon_threadsafe(result_queue.put_nowait, payload)

            def handle_canceled(evt: speechsdk.SpeechRecognitionCanceledEventArgs) -> None:
                try:
                    details = speechsdk.CancellationDetails.from_result(evt.result)
                    error_details = details.error_details
                    cancel_reason = details.reason
                except Exception:
                    error_details = getattr(evt, 'error_details', 'unavailable')
                    cancel_reason = getattr(evt, 'reason', 'unknown')
                LOGGER.error(
                    "[Azure] ❌ CANCELED for %s | reason=%s | error=%s",
                    speaker_label,
                    cancel_reason,
                    error_details,
                )

            def handle_session_started(evt: speechsdk.SessionEventArgs) -> None:
                LOGGER.info("[Azure] Session started (id=%s) for %s", evt.session_id, speaker_label)

            def handle_session_stopped(evt: speechsdk.SessionEventArgs) -> None:
                LOGGER.info("[Azure] Session stopped (id=%s) for %s", evt.session_id, speaker_label)

            self.recognizer.recognized.connect(handle_final_result)
            self.recognizer.recognizing.connect(handle_partial_result)
            self.recognizer.canceled.connect(handle_canceled)
            self.recognizer.session_started.connect(handle_session_started)
            self.recognizer.session_stopped.connect(handle_session_stopped)

            # Start recognition — .get() waits for the async result but runs fast
            # because it only establishes the Azure connection (not blocking on audio).
            self.recognizer.start_continuous_recognition_async().get()
            LOGGER.info("[Azure] Recognizer started for %s in meeting %s", speaker_label, meeting_id)
            return True

        except Exception as exc:
            LOGGER.error("[Azure] Failed to start recognizer for %s: %s", speaker_label, exc)
            self.recognizer = None
            self.push_stream = None
            return False

    def write_chunk(self, chunk: bytes) -> None:
        """Push raw PCM audio bytes into the Azure recognition stream."""
        if self.push_stream:
            self.push_stream.write(chunk)
            self._chunks_written += 1
            self._bytes_written += len(chunk)

            # Log the very first chunk written to Azure to confirm audio is flowing
            if self._chunks_written == 1:
                LOGGER.info("[Azure] ▶ First chunk written to push stream (%d bytes)", len(chunk))

            # Detect silence: check RMS energy of the Int16 PCM chunk
            if len(chunk) >= 2:
                samples = struct.unpack_from(f'<{len(chunk)//2}h', chunk)
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                if rms < 50:  # near-silence threshold (out of 32767 max)
                    self._silent_chunks += 1

            # Log audio stats every ~1 second (25 chunks × 40ms)
            if self._chunks_written % 25 == 0:
                silence_pct = (self._silent_chunks / self._chunks_written) * 100
                LOGGER.info(
                    "[Azure] Audio stats — chunks=%d, bytes=%d KB, silence=%.0f%%",
                    self._chunks_written,
                    self._bytes_written // 1024,
                    silence_pct,
                )
                if silence_pct > 90:
                    LOGGER.warning(
                        "[Azure] ⚠️  >90%% of audio is silence — mic may be muted or not capturing audio!"
                    )

    def stop(self) -> None:
        """Stop continuous recognition and close the push stream."""
        if self.recognizer:
            try:
                self.recognizer.stop_continuous_recognition_async().get()
            except Exception as exc:
                LOGGER.debug("[Azure] Stop error: %s", exc)

        if self.push_stream:
            try:
                self.push_stream.close()
            except Exception as exc:
                LOGGER.debug("[Azure] Stream close error: %s", exc)

        self.recognizer = None
        self.push_stream = None
