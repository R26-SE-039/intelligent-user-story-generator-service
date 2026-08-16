"""Domain models for conflict detection and resolution."""

from __future__ import annotations
from pydantic import BaseModel


class Conflict(BaseModel):
    """Conflict between requirements."""
    conflict_id: str
    requirement_a_id: str
    requirement_b_id: str
    conflict_type: str
    severity: str
    explanation: str
    source_meeting_id: str | None = None
    source_meeting_title: str | None = None
    requirement_a_text: str | None = None
    requirement_b_text: str | None = None
    status: str = "active"
    suggested_resolution: str | None = None
    resolved_by: str | None = None
    resolved_at: str | None = None


class ConflictResolutionRequest(BaseModel):
    """Request model for BA conflict resolution."""
    conflict_id: str
    resolution_type: str  # 'apply_suggestion', 'keep_a', 'keep_b', 'edit_a', 'edit_b', 'merge', 'accept_duplicate', 'dismiss'
    edited_text_a: str | None = None
    edited_text_b: str | None = None
    merged_text: str | None = None
    user_id: str | None = None
