"""Layer 5 — Validation Engine Orchestrator.

Combines results from all four validation layers into a single
:class:`ValidationResult` per user story using the following weights:

    Evidence Score    : 40%
    Semantic Similarity: 25%
    INVEST Score      : 20%
    Rule Validation   : 10%
    Hallucination Risk:  5%

Usage::

    engine = ValidationEngine(genai_client=client, model="gemini-3.1-flash-lite")
    results = engine.validate_batch(batch, evidence_chunks)
"""

from __future__ import annotations

import logging
from typing import Sequence

from google import genai

from src.models.transcript import Chunk
from src.models.user_story import GeneratedStory, StoryBatch, StoryIssue, ValidationResult

from .evidence_validator import EvidenceValidator
from .hallucination_detector import HallucinationDetector
from .invest_validator import InvestValidator
from .rule_validator import validate_rules

LOGGER = logging.getLogger(__name__)

# Scoring weights (must sum to 1.0)
_W_EVIDENCE = 0.40
_W_SEMANTIC = 0.25
_W_INVEST = 0.20
_W_RULE = 0.10
_W_HALLUCINATION = 0.05

# Approval thresholds
_APPROVED_THRESHOLD = 80.0
_NEEDS_REVIEW_THRESHOLD = 50.0


def _compute_overall_score(
    evidence_score: float,      # 0–100
    semantic_similarity: float, # 0–1
    invest_score_5: float,      # 0–5
    rule_score: float,          # 0–100
    hallucination_score: float, # 0–1 (higher = worse)
) -> float:
    """Compute the weighted overall quality score (0–100)."""
    # Normalise all components to 0–100 for weighting
    evidence_norm = evidence_score                     # already 0–100
    semantic_norm = semantic_similarity * 100.0        # 0–1 → 0–100
    invest_norm = (invest_score_5 / 5.0) * 100.0      # 0–5 → 0–100
    rule_norm = rule_score                             # already 0–100
    # Hallucination: lower is better → invert
    hallucination_norm = (1.0 - hallucination_score) * 100.0  # 0–1 → 0–100

    score = (
        _W_EVIDENCE * evidence_norm
        + _W_SEMANTIC * semantic_norm
        + _W_INVEST * invest_norm
        + _W_RULE * rule_norm
        + _W_HALLUCINATION * hallucination_norm
    )
    return round(score, 2)


def _determine_status(overall: float) -> str:
    if overall >= _APPROVED_THRESHOLD:
        return "Approved"
    if overall >= _NEEDS_REVIEW_THRESHOLD:
        return "Needs Review"
    return "Rejected"


def _build_recommendation(
    status: str,
    issues: list[StoryIssue],
    suggestions: list[str],
    unsupported_claims: list[str],
) -> str:
    if status == "Approved" and not issues:
        return "User story is validated and ready for the product backlog."

    parts: list[str] = []
    if status == "Rejected":
        parts.append("This story has critical quality issues and should be rewritten.")
    elif status == "Needs Review":
        parts.append("This story needs improvements before it is backlog-ready.")

    if unsupported_claims:
        parts.append(f"Unsupported claims detected: {'; '.join(unsupported_claims[:3])}.")
    if suggestions:
        parts.append("Suggestions: " + " | ".join(suggestions[:3]) + ".")

    high_issues = [i for i in issues if i.severity == "high"]
    if high_issues:
        parts.append(
            "Critical issues: " + "; ".join(i.detail for i in high_issues[:2]) + "."
        )

    return " ".join(parts) if parts else "Review the listed issues and address them."


class ValidationEngine:
    """Orchestrate all validation layers and produce a :class:`ValidationResult`
    for each story in a :class:`StoryBatch`.

    This class is designed to be modular — additional validators can be
    plugged in by extending the ``validate_batch`` method.
    """

    def __init__(self, genai_client: genai.Client | None, model: str) -> None:
        self._client = genai_client
        self._model = model

        if genai_client is not None:
            self._evidence_validator = EvidenceValidator(genai_client)
            self._hallucination_detector = HallucinationDetector(genai_client, model)
            self._invest_validator = InvestValidator(genai_client, model)
        else:
            self._evidence_validator = None
            self._hallucination_detector = None
            self._invest_validator = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_batch(
        self,
        batch: StoryBatch,
        evidence_chunks: list[Chunk],
    ) -> list[ValidationResult]:
        """Validate every story in the batch and return one result per story."""
        if not batch.stories:
            return []

        # Layer 1: Rule checks (fast, no LLM)
        rule_results = validate_rules(batch)

        results: list[ValidationResult] = []
        for story in batch.stories:
            result = self._validate_single(story, evidence_chunks, rule_results)
            results.append(result)
            LOGGER.info(
                "[ValidationEngine] story_id=%s status=%s overall=%.1f",
                story.story_id,
                result.status,
                result.overall_quality_score,
            )

        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _validate_single(
        self,
        story: GeneratedStory,
        evidence_chunks: list[Chunk],
        rule_results: dict[str, tuple[list[StoryIssue], float]],
    ) -> ValidationResult:
        # Layer 1 — Rule
        rule_issues, rule_score = rule_results.get(story.story_id, ([], 100.0))

        # Layer 2 — Evidence (Gemini Embeddings)
        if self._evidence_validator is not None:
            semantic_similarity, evidence_score = self._evidence_validator.validate(
                story.story, evidence_chunks
            )
        else:
            LOGGER.debug("[ValidationEngine] No GenAI client — skipping evidence validation.")
            semantic_similarity, evidence_score = 0.5, 50.0

        # Layer 3 — Hallucination (Gemini LLM)
        if self._hallucination_detector is not None:
            hallucination_score, _confidence, unsupported_claims = (
                self._hallucination_detector.detect(story.story, evidence_chunks)
            )
        else:
            hallucination_score, _confidence, unsupported_claims = 0.5, 0.5, []

        # Layer 4 — INVEST (Gemini LLM)
        if self._invest_validator is not None:
            invest_breakdown, invest_score_5, suggestions = (
                self._invest_validator.validate(story.story, story.acceptance_criteria)
            )
        else:
            from src.models.user_story import InvestScore
            invest_breakdown = InvestScore()
            invest_score_5, suggestions = 5.0, []

        # Aggregate unsupported claim issues into the issues list
        all_issues = list(rule_issues)
        for claim in unsupported_claims:
            all_issues.append(
                StoryIssue(
                    story_id=story.story_id,
                    severity="high",
                    issue_type="unsupported_claim",
                    detail=claim,
                )
            )

        # Layer 5 — Overall score
        overall = _compute_overall_score(
            evidence_score=evidence_score,
            semantic_similarity=semantic_similarity,
            invest_score_5=invest_score_5,
            rule_score=rule_score,
            hallucination_score=hallucination_score,
        )
        status = _determine_status(overall)
        recommendation = _build_recommendation(
            status=status,
            issues=all_issues,
            suggestions=suggestions,
            unsupported_claims=unsupported_claims,
        )

        return ValidationResult(
            story_id=story.story_id,
            semantic_similarity=semantic_similarity,
            evidence_score=evidence_score,
            invest_score=invest_score_5,
            hallucination_score=hallucination_score,
            rule_score=rule_score,
            overall_quality_score=overall,
            status=status,
            issues=all_issues,
            recommendation=recommendation,
            invest_breakdown=invest_breakdown,
        )
