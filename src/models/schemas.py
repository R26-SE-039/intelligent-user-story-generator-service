"""API DTO schemas and public models API."""

from __future__ import annotations
from pydantic import BaseModel

# Re-export domain models for backward compatibility
from .transcript import Utterance, Transcript, Chunk
from .requirement import Requirement
from .conflict import Conflict
from .user_story import GeneratedStory, StoryBatch, StoryIssue

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

__all__ = [
    "Utterance", "Transcript", "Chunk",
    "Requirement", "Conflict",
    "GeneratedStory", "StoryBatch", "StoryIssue",
    "IngestResponse", "GenerateStoriesRequest", "GenerateStoriesResponse",
    "PipelineRunRequest", "PipelineRunResponse"
]
