"""Domain models for requirements."""

from __future__ import annotations
from pydantic import BaseModel

class Requirement(BaseModel):
    """Structured requirement extracted from meeting."""
    requirement_id: str
    meeting_id: str | None = None
    requirement_text: str
    requirement_type: str
    status: str = "active"
