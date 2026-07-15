"""Repository for transcript data."""

from __future__ import annotations
from uuid import uuid4

from src.db.postgres import PostgresGateway
from src.models.transcript import Transcript
from src.utils.helpers import utc_now


class TranscriptRepository:
    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save(self, transcript: Transcript) -> None:
        # Save Transcript
        self._gateway.upsert(
            self._gateway.settings.transcripts_table,
            {
                "id": transcript.transcript_id,
                "meeting_id": transcript.meeting_id,
                "created_at": utc_now(),
            },
            on_conflict="id"
        )

        # Save Utterances
        utterance_rows = []
        for index, item in enumerate(transcript.utterances):
            utterance_rows.append(
                {
                    "id": str(uuid4()), # We generate a UUID for the utterance
                    "transcript_id": transcript.transcript_id,
                    "speaker_id": item.speaker_id,
                    "speaker_name": item.speaker,
                    "utterance_text": item.text,
                    "start_time": item.timestamp_start,
                    "end_time": item.timestamp_end,
                    "confidence_score": getattr(item, "confidence_score", None),
                    "utterance_type": getattr(item, "utterance_type", None)
                }
            )

        if utterance_rows:
            self._gateway.upsert(
                self._gateway.settings.transcript_utterances_table, 
                utterance_rows, 
                on_conflict="id"
            )
