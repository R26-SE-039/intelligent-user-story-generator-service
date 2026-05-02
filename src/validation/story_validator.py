"""Validation checks for generated user stories."""

from __future__ import annotations

from ..models.schemas import StoryBatch, StoryIssue


def validate_stories(batch: StoryBatch) -> list[StoryIssue]:
    """Validate story quality constraints and return detected issues."""
    issues: list[StoryIssue] = []

    for story in batch.stories:
        if not story.story.lower().startswith("as a "):
            issues.append(
                StoryIssue(
                    story_id=story.story_id,
                    severity="high",
                    issue_type="invalid_format",
                    detail="Story must start with 'As a ...'.",
                )
            )

        if not story.evidence_refs:
            issues.append(
                StoryIssue(
                    story_id=story.story_id,
                    severity="high",
                    issue_type="unsupported_claim",
                    detail="Every story must include evidence references.",
                )
            )

        if not story.acceptance_criteria:
            issues.append(
                StoryIssue(
                    story_id=story.story_id,
                    severity="medium",
                    issue_type="missing_acceptance_criteria",
                    detail="At least one acceptance criterion is required.",
                )
            )

        for criterion in story.acceptance_criteria:
            lowered = criterion.lower()
            if not ("given" in lowered and "when" in lowered and "then" in lowered):
                issues.append(
                    StoryIssue(
                        story_id=story.story_id,
                        severity="low",
                        issue_type="weak_acceptance_criterion",
                        detail="Acceptance criteria should follow Given/When/Then style.",
                    )
                )
                break

    return issues
