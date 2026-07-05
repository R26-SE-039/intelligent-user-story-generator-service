"""Repository for meeting and chat data."""

from __future__ import annotations
from typing import Any
from uuid import uuid4

from src.db.postgres import PostgresGateway
from src.utils.helpers import utc_now


class MeetingRepository:
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

    def end_meeting(self, meeting_id: str) -> None:
        self._gateway.update(
            self._gateway.settings.meetings_table,
            {"end_time": utc_now(), "status": "completed"},
            eq={"id": meeting_id}
        )

    def add_participant(self, meeting_id: str, user_id: str) -> None:
        table_name = getattr(self._gateway.settings, "meeting_participants_table", "meeting_participants")
        existing = self._gateway.select(
            table_name,
            eq={"meeting_id": meeting_id, "user_id": user_id}
        )
        if not existing:
            self._gateway.insert(
                table_name,
                {
                    "id": str(uuid4()),
                    "meeting_id": meeting_id,
                    "user_id": user_id,
                    "joined_at": utc_now(),
                }
            )

    def save_chat(self, meeting_id: str, sender_id: str, text: str) -> None:
        self._gateway.insert(
            self._gateway.settings.chat_messages_table,
            {
                "id": str(uuid4()),
                "meeting_id": meeting_id,
                "sender_id": sender_id,
                "message": text,
                "created_at": utc_now(),
            }
        )

    def get_chats(self, meeting_id: str) -> list[dict[str, Any]]:
        return self._gateway.select(
            self._gateway.settings.chat_messages_table,
            eq={"meeting_id": meeting_id}
        )

    def finalize_transcript(self, meeting_id: str, captions: list[dict[str, Any]], mappings: list[dict[str, str]] = None) -> dict[str, Any] | None:
        """Consolidate real-time captions into the final transcripts and utterances tables."""
        if not captions:
            return None

        transcript_id = str(uuid4())

        self._gateway.upsert(
            self._gateway.settings.transcripts_table,
            {
                "id": transcript_id,
                "meeting_id": meeting_id,
                "created_at": utc_now(),
            },
            on_conflict="id"
        )

        utterance_rows = []
        for cap in captions:
            utterance_rows.append({
                "id": cap.get("id") or str(uuid4()),
                "transcript_id": transcript_id,
                "speaker_id": cap.get("speaker_id"),
                "speaker_name": cap.get("speaker", ""),
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
            
        if mappings:
            # Reusing the existing requirement saving logic, so we need requirement repository here.
            # To avoid circular imports, we just run the query directly using postgres gateway.
            # We already have save_utterance_mappings in RequirementRepository, but we can't easily inject it.
            # Wait, MeetingRepository shouldn't depend on RequirementRepository.
            # Let's just do a direct upsert/insert ON CONFLICT DO NOTHING here.
            table = self._gateway.settings.requirement_utterance_mapping_table
            if mappings:
                columns = list(mappings[0].keys())
                values_list = []
                for m in mappings:
                    values_list.append(tuple(self._gateway._format_value(m.get(c)) for c in columns))
                    
                col_str = ", ".join([f'"{c}"' for c in columns])
                query = f'INSERT INTO "{table}" ({col_str}) VALUES %s ON CONFLICT DO NOTHING'
                
                from psycopg2.extras import execute_values
                with self._gateway._get_connection() as conn:
                    with conn.cursor() as cur:
                        execute_values(cur, query, values_list)
                    conn.commit()

        return {"transcript_id": transcript_id, "utterance_count": len(utterance_rows)}
