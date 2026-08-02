"""Layer 1 — Rule-Based Validation.

Validates every generated user story against structural rules:
  - Standard "As a / I want / So that" format using regex
  - Missing or empty fields (title, story text, acceptance criteria)
  - Duplicate story detection (same title, case-insensitive)
  - Invalid format structure
"""

from __future__ import annotations

import re
from collections import Counter

from src.models.user_story import GeneratedStory, StoryBatch, StoryIssue

# Regex that loosely matches the 3-clause user story structure
_STORY_FORMAT_RE = re.compile(
    r"(?i)as\s+an?\s+.+?,?\s+i\s+want\s+.+?,?\s+so\s+that\s+.+"
)


def _check_format(story: GeneratedStory) -> list[StoryIssue]:
    """Validate that the story text follows 'As a / I want / So that'."""
    issues: list[StoryIssue] = []
    text = (story.story or "").strip()

    if not text:
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="high",
                issue_type="empty_story",
                detail="Story text is empty.",
            )
        )
        return issues

    if not text.lower().startswith("as a") and not text.lower().startswith("as an"):
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="high",
                issue_type="invalid_format",
                detail="Story must start with 'As a <role>' or 'As an <role>'.",
            )
        )

    if "i want" not in text.lower():
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="high",
                issue_type="missing_goal",
                detail="Story is missing the 'I want <goal>' clause.",
            )
        )

    if "so that" not in text.lower():
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="medium",
                issue_type="missing_benefit",
                detail="Story is missing the 'So that <benefit>' clause.",
            )
        )

    return issues


def _check_missing_fields(story: GeneratedStory) -> list[StoryIssue]:
    """Validate that required fields are present and non-empty."""
    issues: list[StoryIssue] = []

    if not (story.title or "").strip():
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="medium",
                issue_type="missing_title",
                detail="Story is missing a title.",
            )
        )

    if not story.evidence_refs:
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="high",
                issue_type="unsupported_claim",
                detail="Every story must include evidence references from the transcript.",
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

    return issues


def _check_acceptance_criteria(story: GeneratedStory) -> list[StoryIssue]:
    """Validate that at least one AC follows Given/When/Then style."""
    issues: list[StoryIssue] = []
    if not story.acceptance_criteria:
        return issues

    has_gwt = any(
        "given" in ac.lower() and "when" in ac.lower() and "then" in ac.lower()
        for ac in story.acceptance_criteria
    )
    if not has_gwt:
        issues.append(
            StoryIssue(
                story_id=story.story_id,
                severity="low",
                issue_type="weak_acceptance_criterion",
                detail="Acceptance criteria should follow the Given/When/Then format.",
            )
        )
    return issues


def _check_duplicates(batch: StoryBatch) -> list[StoryIssue]:
    """Detect duplicate stories by normalised title."""
    issues: list[StoryIssue] = []
    title_counts: Counter[str] = Counter()
    story_by_title: dict[str, str] = {}

    for story in batch.stories:
        key = (story.title or "").strip().lower()
        title_counts[key] += 1
        if key not in story_by_title:
            story_by_title[key] = story.story_id

    for story in batch.stories:
        key = (story.title or "").strip().lower()
        if title_counts[key] > 1 and story_by_title[key] != story.story_id:
            issues.append(
                StoryIssue(
                    story_id=story.story_id,
                    severity="medium",
                    issue_type="duplicate_story",
                    detail=f"Duplicate story title detected: '{story.title}'.",
                )
            )
    return issues


def validate_rules(batch: StoryBatch) -> dict[str, tuple[list[StoryIssue], float]]:
    """Run all rule-based checks for each story.

    Returns a dict keyed by story_id mapping to
    ``(issues_list, rule_score)`` where rule_score is 0–100.
    """
    duplicate_issues = _check_duplicates(batch)
    # Group duplicate issues by story_id for easy merging
    dup_by_id: dict[str, list[StoryIssue]] = {}
    for iss in duplicate_issues:
        dup_by_id.setdefault(iss.story_id, []).append(iss)

    results: dict[str, tuple[list[StoryIssue], float]] = {}

    for story in batch.stories:
        story_issues: list[StoryIssue] = []
        story_issues.extend(_check_format(story))
        story_issues.extend(_check_missing_fields(story))
        story_issues.extend(_check_acceptance_criteria(story))
        story_issues.extend(dup_by_id.get(story.story_id, []))

        # Rule score: deduct per severity
        penalty = sum(
            {"high": 25, "medium": 10, "low": 5}.get(iss.severity, 5)
            for iss in story_issues
        )
        rule_score = max(0.0, 100.0 - penalty)
        results[story.story_id] = (story_issues, rule_score)

    return results
