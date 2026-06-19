"""Supabase-backed persistence helpers for the text-to-user-stories service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from postgres_gateway import PostgresGateway
from src.models.schemas import Chunk, GeneratedStory, StoryIssue, Transcript


class TextPersistence:
    """Persist transcripts, chunks, and generated stories to PostgreSQL."""

    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save_transcript(self, transcript: Transcript) -> None:
        participants = transcript.participants or sorted({item.speaker for item in transcript.utterances})
        self._gateway.upsert(
            self._gateway.settings.transcripts_table,
            {
                "transcript_id": transcript.transcript_id,
                "project_id": transcript.project_id,
                "source": transcript.source,
                "participants": participants,
                "metadata": {
                    "product_area": transcript.product_area,
                },
                "updated_at": _utc_now(),
            },
            on_conflict="transcript_id"
        )

        utterance_rows = []
        for index, item in enumerate(transcript.utterances):
            utterance_rows.append(
                {
                    "utterance_id": f"{transcript.transcript_id}:{index}",
                    "transcript_id": transcript.transcript_id,
                    "utterance_index": index,
                    "speaker": item.speaker,
                    "text": item.text,
                    "timestamp_start": item.timestamp_start,
                    "timestamp_end": item.timestamp_end,
                    "metadata": {},
                }
            )

        if utterance_rows:
            self._gateway.upsert(
                self._gateway.settings.utterances_table, 
                utterance_rows, 
                on_conflict="utterance_id"
            )

    def save_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return

        rows = []
        for chunk in chunks:
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "transcript_id": chunk.transcript_id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "speakers": chunk.speakers,
                    "timestamp_start": chunk.timestamp_start,
                    "timestamp_end": chunk.timestamp_end,
                    "metadata": chunk.metadata,
                }
            )

        self._gateway.upsert(self._gateway.settings.chunks_table, rows, on_conflict="chunk_id")

    def save_story_run(
        self,
        *,
        transcript_id: str | None,
        project_id: str | None = None,
        query: str,
        stories: list[GeneratedStory],
        issues: list[StoryIssue],
        evidence_chunk_ids: list[str],
    ) -> None:
        story_run_id = f"run-{uuid4()}"
        self._gateway.insert(
            self._gateway.settings.story_runs_table,
            {
                "story_run_id": story_run_id,
                "transcript_id": transcript_id,
                "project_id": project_id,
                "query": query,
                "issues": [item.model_dump() for item in issues],
                "evidence_chunk_ids": evidence_chunk_ids,
                "created_at": _utc_now(),
            },
        )

        if not stories:
            return

        story_rows = []
        for story in stories:
            story_rows.append(
                {
                    "generated_story_id": f"{story_run_id}:{story.story_id}",
                    "story_run_id": story_run_id,
                    "transcript_id": transcript_id,
                    "story_id": story.story_id,
                    "title": story.title,
                    "story": story.story,
                    "acceptance_criteria": story.acceptance_criteria,
                    "priority": story.priority,
                    "confidence": story.confidence,
                    "status": story.status,
                    "clarification_questions": story.clarification_questions,
                    "evidence_refs": story.evidence_refs,
                }
            )

        self._gateway.insert(self._gateway.settings.stories_table, story_rows)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()