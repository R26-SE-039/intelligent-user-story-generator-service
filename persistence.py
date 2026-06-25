"""PostgreSQL-backed persistence helpers for the text-to-user-stories service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from postgres_gateway import PostgresGateway
from src.models.schemas import Requirement, GeneratedStory, StoryIssue, Transcript, Conflict


class TextPersistence:
    """Persist transcripts, stories, and requirements to PostgreSQL."""

    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save_transcript(self, transcript: Transcript) -> None:
        # Save Transcript
        self._gateway.upsert(
            self._gateway.settings.transcripts_table,
            {
                "id": transcript.transcript_id,
                "meeting_id": transcript.meeting_id,
                "created_at": _utc_now(),
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
                    "utterance_text": item.text,
                    "start_time": item.timestamp_start,
                    "end_time": item.timestamp_end,
                    "confidence_score": getattr(item, "confidence_score", None)
                }
            )

        if utterance_rows:
            self._gateway.upsert(
                self._gateway.settings.transcript_utterances_table, 
                utterance_rows, 
                on_conflict="id"
            )

    def save_requirements(self, requirements: list[Requirement]) -> None:
        if not requirements:
            return

        rows = []
        for req in requirements:
            rows.append(
                {
                    "id": req.requirement_id,
                    "meeting_id": req.meeting_id,
                    "requirement_text": req.requirement_text,
                    "requirement_type": req.requirement_type,
                    "status": req.status,
                    "created_at": _utc_now(),
                }
            )
        self._gateway.upsert(self._gateway.settings.requirements_table, rows, on_conflict="id")

    def save_requirement_embeddings(self, embeddings: list[dict[str, any]]) -> None:
        # Not fully implemented without pgvector python wrapper, left as placeholder for pgvector inserts
        pass

    def save_requirement_utterance_mappings(self, mappings: list[dict[str, str]]) -> None:
        if not mappings:
            return
        self._gateway.upsert(self._gateway.settings.requirement_utterance_mapping_table, mappings, on_conflict="requirement_id")

    def save_user_stories(
        self,
        *,
        meeting_id: str | None = None,
        stories: list[GeneratedStory]
    ) -> None:
        if not stories:
            return

        story_rows = []
        ac_rows = []
        
        for story in stories:
            story_id = story.story_id
            story_rows.append(
                {
                    "id": story_id,
                    "meeting_id": meeting_id,
                    "title": story.title,
                    "story": story.story,
                    "priority": story.priority,
                    "status": story.status,
                }
            )
            
            for ac in story.acceptance_criteria:
                ac_rows.append(
                    {
                        "id": str(uuid4()),
                        "user_story_id": story_id,
                        "criteria": ac
                    }
                )

        self._gateway.upsert(self._gateway.settings.user_stories_table, story_rows, on_conflict="id")
        self._gateway.upsert(self._gateway.settings.acceptance_criteria_table, ac_rows, on_conflict="id")

    def save_user_story_requirement_mappings(self, mappings: list[dict[str, str]]) -> None:
        if not mappings:
            return
        # mappings format: [{"user_story_id": "...", "requirement_id": "..."}]
        self._gateway.upsert(self._gateway.settings.user_story_requirement_mapping_table, mappings, on_conflict="user_story_id")

    def save_conflicts(self, conflicts: list[Conflict]) -> None:
        if not conflicts:
            return
        
        rows = []
        for conflict in conflicts:
            rows.append(
                {
                    "id": conflict.conflict_id,
                    "requirement_a_id": conflict.requirement_a_id,
                    "requirement_b_id": conflict.requirement_b_id,
                    "conflict_type": conflict.conflict_type,
                    "severity": conflict.severity,
                    "explanation": conflict.explanation
                }
            )
        self._gateway.upsert(self._gateway.settings.conflicts_table, rows, on_conflict="id")

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()