"""Domain models for user stories and generation."""

from __future__ import annotations
import uuid
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class InvestScore(BaseModel):
    """Numeric INVEST quality scores per principle (0.0 – 1.0 each)."""
    Independent: float = Field(default=1.0, ge=0.0, le=1.0)
    Negotiable: float = Field(default=1.0, ge=0.0, le=1.0)
    Valuable: float = Field(default=1.0, ge=0.0, le=1.0)
    Estimable: float = Field(default=1.0, ge=0.0, le=1.0)
    Small: float = Field(default=1.0, ge=0.0, le=1.0)
    Testable: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def overall(self) -> float:
        """Average score across all six INVEST principles (0.0 – 1.0)."""
        values = [
            self.Independent, self.Negotiable, self.Valuable,
            self.Estimable, self.Small, self.Testable,
        ]
        return round(sum(values) / len(values), 4)



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

    @field_validator("story_id", mode="before")
    @classmethod
    def ensure_uuid(cls, v: str) -> str:
        """Replace LLM-assigned labels like 'US-001' with a real UUID."""
        try:
            uuid.UUID(str(v))
            return str(v)
        except (ValueError, AttributeError):
            return str(uuid4())


class StoryBatch(BaseModel):
    """Collection of generated stories."""
    stories: list[GeneratedStory]


class StoryIssue(BaseModel):
    """Validation issue found in generated stories."""
    story_id: str
    severity: Literal["high", "medium", "low"]
    issue_type: str
    detail: str


class ValidationResult(BaseModel):
    """Full validation result for a single user story.

    Produced by the 5-layer ValidationEngine and persisted to
    the ``user_story_validations`` PostgreSQL table.
    """
    story_id: str

    # Layer scores
    semantic_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_score: float = Field(default=0.0, ge=0.0, le=100.0)
    invest_score: float = Field(default=0.0, ge=0.0, le=5.0)
    hallucination_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rule_score: float = Field(default=100.0, ge=0.0, le=100.0)

    # Aggregated
    overall_quality_score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["Approved", "Needs Review", "Rejected"] = "Needs Review"

    # Details
    issues: list[StoryIssue] = Field(default_factory=list)
    recommendation: str = ""

    # Per-principle INVEST breakdown (optional, included when available)
    invest_breakdown: InvestScore | None = None
