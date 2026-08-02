"""Coordinator service for real-time live meeting WebSocket sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from src.repositories.meeting_repository import MeetingRepository
from src.services.speech.azure_client import AzureSpeechClient
from src.services.speech.azure_stream_service import AzureStreamService
from src.services.speech.live_meeting_service import LiveMeetingService
from src.services.speech.transcription_service import TranscriptionService
from src.services.speech.websocket_manager import WebSocketManager

LOGGER = logging.getLogger(__name__)

# Optimal audio chunk size for Azure Speech SDK PushInputStream (1280 bytes = 40ms @ 16kHz)
MIN_CHUNK_BYTES = 1280


class LiveMeetingCoordinator:
    """Orchestrates live voice streaming, Azure speech recognition, real-time
    requirement extraction, and room broadcasting for active meeting sessions.
    """

    def __init__(
        self,
        ws_manager: WebSocketManager,
        azure_speech: AzureSpeechClient,
        live_meeting_service: LiveMeetingService,
        meeting_repo: MeetingRepository,
        transcription_service: TranscriptionService,
    ) -> None:
        self.ws_manager = ws_manager
        self.azure_speech = azure_speech
        self.live_meeting_service = live_meeting_service
        self.meeting_repo = meeting_repo
        self.transcription_service = transcription_service

    async def handle_websocket_session(
        self,
        websocket: WebSocket,
        meeting_id: str,
        name: str = "Anonymous",
        role: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Handle the complete lifecycle of a live meeting WebSocket session."""
        conn_id = str(uuid.uuid4())
        speaker_label = f"{name} ({role})" if role else name
        loop = asyncio.get_running_loop()

        # 1. Accept connection and register participant
        await self.ws_manager.connect(meeting_id, conn_id, name, websocket)

        # 2. Start Azure push-stream recognizer
        stream_service = AzureStreamService(self.azure_speech)
        result_queue: asyncio.Queue = asyncio.Queue()

        started = await loop.run_in_executor(
            None,
            lambda: stream_service.start(
                conn_id=conn_id,
                speaker_label=speaker_label,
                meeting_id=meeting_id,
                loop=loop,
                result_queue=result_queue,
            ),
        )

        if not started:
            LOGGER.error("[Coordinator] Azure recognizer failed to start for %s — closing session.", speaker_label)
            await self.ws_manager.disconnect(meeting_id, conn_id, websocket, self.meeting_repo)
            return

        # 3. Background worker: consume recognition events and broadcast/process them
        async def queue_worker() -> None:
            try:
                while True:
                    data = await result_queue.get()
                    await self.ws_manager.broadcast_to_meeting(meeting_id, data)

                    if data.get("type") == "transcription" and data.get("data", {}).get("is_final"):
                        try:
                            caption = self.transcription_service.push_caption(
                                meeting_id,
                                data["data"]["speaker_name"],
                                data["data"]["text"],
                                speaker_id=data["data"].get("speaker_id"),
                                timestamp_start=data["data"].get("timestamp_start"),
                                timestamp_end=data["data"].get("timestamp_end"),
                            )
                            asyncio.create_task(
                                self.live_meeting_service.process_utterance(
                                    meeting_id=meeting_id,
                                    utterance_text=data["data"]["text"],
                                    caption_id=caption.id,
                                )
                            )
                        except ValueError:
                            pass

                    result_queue.task_done()
            except asyncio.CancelledError:
                pass

        worker_task = asyncio.create_task(queue_worker())

        bytes_received = 0
        audio_buffer = bytearray()

        # 4. Main WebSocket receive loop
        try:
            while True:
                msg = await websocket.receive()

                if msg.get("type") == "websocket.disconnect":
                    break

                if msg.get("bytes") is not None:
                    chunk = msg["bytes"]
                    if bytes_received == 0:
                        LOGGER.info(
                            "[WS] First audio chunk received from %s (%d bytes)",
                            speaker_label, len(chunk),
                        )
                    
                    bytes_received += len(chunk)
                    audio_buffer.extend(chunk)

                    # Log audio streaming progress every ~128 KB (~4 seconds)
                    total_chunks = bytes_received // MIN_CHUNK_BYTES
                    if total_chunks > 0 and total_chunks % 100 == 0 and len(audio_buffer) < len(chunk):
                        LOGGER.info(
                            "[WS] Streaming audio from %s: %d KB received",
                            speaker_label, bytes_received // 1024,
                        )

                    # Flush to Azure in optimal 1280-byte (40ms) blocks
                    while len(audio_buffer) >= MIN_CHUNK_BYTES:
                        flush_chunk = bytes(audio_buffer[:MIN_CHUNK_BYTES])
                        audio_buffer = audio_buffer[MIN_CHUNK_BYTES:]
                        stream_service.write_chunk(flush_chunk)

                elif msg.get("text") is not None:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue

                    msg_type = data.get("type")
                    if msg_type == "chat":
                        await self.ws_manager.handle_chat_message(
                            meeting_id=meeting_id,
                            sender_name=data.get("sender", name),
                            text=data.get("text", ""),
                            user_id=user_id,
                            meeting_repo=self.meeting_repo,
                        )
                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            LOGGER.warning("[Coordinator] Unexpected error for %s: %s", speaker_label, exc)
        finally:
            # Flush any remaining audio in buffer before stopping
            if audio_buffer:
                stream_service.write_chunk(bytes(audio_buffer))
                audio_buffer.clear()

            worker_task.cancel()
            await loop.run_in_executor(None, stream_service.stop)
            await self.ws_manager.disconnect(meeting_id, conn_id, websocket, self.meeting_repo)
            LOGGER.info("[Coordinator] Session ended for %s in meeting %s", speaker_label, meeting_id)
