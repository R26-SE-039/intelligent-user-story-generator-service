"""Domain models for transcripts and utterances."""

from __future__ import annotations
from pydantic import BaseModel, Field

class Utterance(BaseModel):
    """Single speaker utterance in a transcript."""
    speaker: str
    speaker_id: str | None = None
    text: str
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    confidence_score: float | None = None

class Transcript(BaseModel):
    """Transcript payload to ingest and index."""
    transcript_id: str
    meeting_id: str | None = None
    project_id: str | None = None
    source: str | None = None
    participants: list[str] = Field(default_factory=list)
    product_area: str | None = None
    utterances: list[Utterance]

class Chunk(BaseModel):
    """Chunked transcript unit used for embedding and retrieval."""
    chunk_id: str
    transcript_id: str
    chunk_index: int
    text: str
    speakers: list[str]
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
