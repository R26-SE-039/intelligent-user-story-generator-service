"""WebSocket connection and broadcasting manager."""

from __future__ import annotations

import logging
import uuid
from typing import Any
from fastapi import WebSocket

from src.repositories.meeting_repository import MeetingRepository
from src.services.speech.transcription_service import TranscriptionService
from src.utils.helpers import utc_now

LOGGER = logging.getLogger(__name__)


class WebSocketManager:
    """Manager for real-time meeting room WebSocket connections and broadcasting."""

    def __init__(self, transcription_service: TranscriptionService) -> None:
        self.transcription_service = transcription_service

    async def connect(
        self,
        meeting_id: str,
        conn_id: str,
        name: str,
        websocket: WebSocket,
    ) -> None:
        """Register a new participant connection and broadcast updated participants list."""
        await websocket.accept()
        self.transcription_service.add_participant(meeting_id, conn_id, name, websocket)
        participants = self.transcription_service.get_participants(meeting_id)
        await self.broadcast_to_meeting(meeting_id, {"type": "participants", "data": participants})

    async def disconnect(
        self,
        meeting_id: str,
        conn_id: str,
        websocket: WebSocket,
        meeting_repo: MeetingRepository,
    ) -> None:
        """Remove participant connection and auto-finalize transcript if room is empty."""
        self.transcription_service.remove_participant(meeting_id, conn_id, websocket)
        participants = self.transcription_service.get_participants(meeting_id)

        if not participants:
            LOGGER.info("[WebSocketManager] Meeting %s room is empty. Auto-finalizing transcript...", meeting_id)
            try:
                captions = self.transcription_service.get_captions(meeting_id)
                captions_dicts = [cap.model_dump() for cap in captions]
                mappings = self.transcription_service.get_requirement_mappings(meeting_id)
                meeting_repo.finalize_transcript(meeting_id, captions_dicts, mappings)
            except ValueError:
                pass
        else:
            await self.broadcast_to_meeting(meeting_id, {"type": "participants", "data": participants})

    async def broadcast_to_meeting(self, meeting_id: str, payload: dict[str, Any]) -> None:
        """Send a JSON payload to all active WebSocket connections in a meeting."""
        connections = self.transcription_service.get_connections(meeting_id)
        for conn in connections:
            try:
                await conn.send_json(payload)
            except Exception:
                pass

    async def handle_chat_message(
        self,
        meeting_id: str,
        sender_name: str,
        text: str,
        user_id: str | None,
        meeting_repo: MeetingRepository,
    ) -> None:
        """Persist a chat message to DB and broadcast to room participants."""
        sender_id = user_id or str(uuid.uuid4())
        meeting_repo.save_chat(meeting_id, sender_id, text)
        chat_payload = {
            "type": "chat",
            "data": {
                "sender": sender_name,
                "text": text,
                "timestamp": utc_now(),
            },
        }
        await self.broadcast_to_meeting(meeting_id, chat_payload)
