"""Domain models for user stories and generation."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

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
