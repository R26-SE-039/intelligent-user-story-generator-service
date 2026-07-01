"""Domain models for conflict detection."""

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
