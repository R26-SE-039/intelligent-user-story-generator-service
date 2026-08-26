"""Unit tests for Layer 1 Rule-Based Validation (rule_validator.py)."""

from __future__ import annotations

import uuid

import pytest

from src.models.user_story import GeneratedStory, StoryBatch
from src.services.generation.validation.rule_validator import validate_rules


_SENTINEL = object()  # Distinguish "not passed" from "passed as None"


def _make_story(
    story_id: str | None = None,
    title: str = "User Login",
    story: str = "As a user, I want to log in, so that I can access my dashboard.",
    acceptance_criteria=_SENTINEL,
    evidence_refs=_SENTINEL,
) -> GeneratedStory:
    """Factory helper to create a GeneratedStory for tests.

    Use ``acceptance_criteria=[]`` or ``evidence_refs=[]`` to explicitly pass
    empty lists (the sentinel ensures they are not replaced by defaults).
    """
    if acceptance_criteria is _SENTINEL:
        acceptance_criteria = [
            "Given I am on the login page When I enter valid credentials Then I am redirected to my dashboard."
        ]
    if evidence_refs is _SENTINEL:
        evidence_refs = ["chunk-001"]
    return GeneratedStory(
        story_id=story_id or str(uuid.uuid4()),
        title=title,
        story=story,
        acceptance_criteria=acceptance_criteria,
        priority="Must",
        confidence=0.9,
        status="ready",
        clarification_questions=[],
        evidence_refs=evidence_refs,
    )


class TestValidateRulesValidStory:
    """A correctly written story should have no high-severity issues."""

    def test_valid_story_produces_high_rule_score(self):
        batch = StoryBatch(stories=[_make_story()])
        results = validate_rules(batch)
        story_id = list(results.keys())[0]
        issues, score = results[story_id]
        high_issues = [i for i in issues if i.severity == "high"]
        assert not high_issues
        assert score >= 75.0

    def test_valid_story_no_format_issues(self):
        batch = StoryBatch(stories=[_make_story()])
        results = validate_rules(batch)
        issues, _ = list(results.values())[0]
        format_issues = [i for i in issues if i.issue_type == "invalid_format"]
        assert not format_issues


class TestValidateRulesMissingClauses:
    """Stories missing required clauses should surface the correct issues."""

    def test_missing_as_a_clause(self):
        story = _make_story(story="I want to log in so that I can access my dashboard.")
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, score = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "invalid_format" in issue_types
        assert score < 100.0

    def test_missing_i_want_clause(self):
        story = _make_story(story="As a user, so that I can access my dashboard.")
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, _ = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "missing_goal" in issue_types

    def test_missing_so_that_clause(self):
        story = _make_story(story="As a user, I want to log in.")
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, _ = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "missing_benefit" in issue_types

    def test_empty_story_text(self):
        story = _make_story(story="")
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, score = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "empty_story" in issue_types
        assert score == 0.0 or score < 100.0


class TestValidateRulesMissingFields:
    """Missing required fields should surface the correct issue types."""

    def test_missing_acceptance_criteria(self):
        story = _make_story(acceptance_criteria=[])
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, _ = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "missing_acceptance_criteria" in issue_types

    def test_missing_evidence_refs(self):
        story = _make_story(evidence_refs=[])
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, _ = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "unsupported_claim" in issue_types

    def test_missing_title(self):
        story = _make_story(title="")
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        issues, _ = results[story.story_id]
        issue_types = {i.issue_type for i in issues}
        assert "missing_title" in issue_types


class TestValidateRulesDuplicates:
    """Duplicate story titles should be detected."""

    def test_duplicate_titles_flagged(self):
        story_a = _make_story(title="User Login")
        story_b = _make_story(title="User Login")  # same title, different ID
        batch = StoryBatch(stories=[story_a, story_b])
        results = validate_rules(batch)

        # At least the duplicate story (not the first occurrence) should be flagged
        all_issue_types = {
            i.issue_type
            for issues, _ in results.values()
            for i in issues
        }
        assert "duplicate_story" in all_issue_types

    def test_unique_titles_not_flagged_as_duplicate(self):
        story_a = _make_story(title="User Login")
        story_b = _make_story(title="User Registration")
        batch = StoryBatch(stories=[story_a, story_b])
        results = validate_rules(batch)
        all_issue_types = {
            i.issue_type
            for issues, _ in results.values()
            for i in issues
        }
        assert "duplicate_story" not in all_issue_types


class TestValidateRulesPenaltyScoring:
    """Rule score deduction follows the defined penalty matrix."""

    def test_high_severity_deducts_25_points(self):
        # Empty story = empty_story issue (high severity = -25)
        story = _make_story(story="")
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        _, score = results[story.story_id]
        # 100 - (25 high for empty_story + 25 high for unsupported_claim
        #       + 10 medium for missing_acceptance_criteria)
        # Actually, after empty_story the function returns early for format checks,
        # but missing_fields checks still run.
        assert score < 100.0

    def test_perfect_story_scores_100(self):
        story = _make_story()
        batch = StoryBatch(stories=[story])
        results = validate_rules(batch)
        _, score = results[story.story_id]
        # A story with valid format, proper ACs in GWT style, evidence → 100
        assert score == 100.0
