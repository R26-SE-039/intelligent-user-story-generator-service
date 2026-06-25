"""Domain and API schemas used across the RAG project."""

from __future__ import annotations

from typing import Literal

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


class Requirement(BaseModel):
    """Structured requirement extracted from meeting."""

    requirement_id: str
    meeting_id: str | None = None
    requirement_text: str
    requirement_type: str
    status: str = "active"


class Conflict(BaseModel):
    """Conflict between requirements."""

    conflict_id: str
    requirement_a_id: str
    requirement_b_id: str
    conflict_type: str
    severity: str
    explanation: str


class GeneratedStory(BaseModel):
    """Structured user story output."""

    story_id: str
    title: str
    story: str
    acceptance_criteria: list[str]
    priority: Literal["Must", "Should", "Could"] = "Should"
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["ready", "needs_clarification"] = "ready"
    clarification_questions: list[str] = Field(default_factory=list)
    evidence_refs: list[str]


class StoryBatch(BaseModel):
    """Collection of generated stories."""

    stories: list[GeneratedStory]


class StoryIssue(BaseModel):
    """Validation issue found in generated stories."""

    story_id: str
    severity: Literal["high", "medium", "low"]
    issue_type: str
    detail: str


class IngestResponse(BaseModel):
    """Response for transcript preprocessing endpoint."""

    transcript_id: str
    chunk_count: int
    chunks: list[Chunk]


class GenerateStoriesRequest(BaseModel):
    """Request for retrieval + generation endpoint."""

    query: str
    top_k: int | None = None
    filters: dict[str, str | int | float | bool] | None = None


class GenerateStoriesResponse(BaseModel):
    """Response containing generated stories and validation findings."""

    query: str
    stories: list[GeneratedStory]
    issues: list[StoryIssue]
    evidence_chunk_ids: list[str]


class PipelineRunRequest(BaseModel):
    """Request payload for end-to-end pipeline execution."""

    transcript: Transcript
    query: str
    top_k: int | None = None
    filters: dict[str, str | int | float | bool] | None = None


class PipelineRunResponse(BaseModel):
    """Combined response for full pipeline execution."""

    transcript_id: str
    indexed_chunks: int
    query: str
    stories: list[GeneratedStory]
    issues: list[StoryIssue]
    evidence_chunk_ids: list[str]
