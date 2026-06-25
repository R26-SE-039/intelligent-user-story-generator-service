"""PostgreSQL-backed persistence helpers for the speech-to-text features."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.speech.schemas import CaptionLine
from postgres_gateway import PostgresGateway


class SpeechPersistence:
    """Persist meeting and transcription results."""

    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save_meeting(self, meeting_data: dict[str, Any]) -> None:
        self._gateway.upsert(
            self._gateway.settings.meetings_table,
            meeting_data,
            on_conflict="id"
        )

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        results = self._gateway.select(
            self._gateway.settings.meetings_table,
            eq={"id": meeting_id}
        )
        return results[0] if results else None

    def save_chat(self, meeting_id: str, sender_id: str, text: str) -> None:
        self._gateway.insert(
            self._gateway.settings.chat_messages_table,
            {
                "id": str(uuid4()),
                "meeting_id": meeting_id,
                "sender_id": sender_id,
                "message": text,
                "created_at": _utc_now(),
            }
        )

    def get_chats(self, meeting_id: str) -> list[dict[str, Any]]:
        return self._gateway.select(
            self._gateway.settings.chat_messages_table,
            eq={"meeting_id": meeting_id}
        )

    def finalize_meeting_transcript(self, meeting_id: str, captions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Consolidate real-time captions into the final transcripts and utterances tables."""
        if not captions:
            return None

        transcript_id = str(uuid4())

        # 1. Save to transcripts table
        self._gateway.upsert(
            self._gateway.settings.transcripts_table,
            {
                "id": transcript_id,
                "meeting_id": meeting_id,
                "created_at": _utc_now(),
            },
            on_conflict="id"
        )

        # 2. Save to utterances table
        utterance_rows = []
        for cap in captions:
            utterance_rows.append({
                "id": str(uuid4()),
                "transcript_id": transcript_id,
                "speaker_id": cap.get("speaker_id"),
                "utterance_text": cap.get("text", ""),
                "start_time": cap.get("timestamp_start"),
                "end_time": cap.get("timestamp_end"),
                "confidence_score": cap.get("confidence", 1.0)
            })

        if utterance_rows:
            self._gateway.upsert(
                self._gateway.settings.transcript_utterances_table,
                utterance_rows,
                on_conflict="id"
            )

        return {"transcript_id": transcript_id, "utterance_count": len(utterance_rows)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
