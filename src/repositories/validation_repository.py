"""Repository for user story validation results.

Persists :class:`ValidationResult` records to the
``user_story_validations`` PostgreSQL table.  The table is created
automatically on first use if it does not already exist.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from src.db.postgres import PostgresGateway
from src.models.user_story import ValidationResult

LOGGER = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_story_validations (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_story_id         UUID NOT NULL REFERENCES user_stories(id) ON DELETE CASCADE,
    status                VARCHAR(50)  NOT NULL DEFAULT 'Needs Review',
    overall_quality_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    recommendation        TEXT,
    semantic_similarity   NUMERIC(6,4) DEFAULT 0,
    evidence_score        NUMERIC(6,2) DEFAULT 0,
    invest_score          NUMERIC(5,2) DEFAULT 0,
    hallucination_score   NUMERIC(6,4) DEFAULT 0,
    rule_score            NUMERIC(6,2) DEFAULT 100,
    invest_breakdown      JSONB,
    issues                JSONB NOT NULL DEFAULT '[]'::jsonb,
    validated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_story_validations_story_id
    ON user_story_validations(user_story_id);

CREATE INDEX IF NOT EXISTS idx_user_story_validations_status
    ON user_story_validations(status);
"""


class ValidationRepository:
    """Save and retrieve validation results from PostgreSQL."""

    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway
        self._table = gateway.settings.user_story_validations_table
        self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, results: list[ValidationResult]) -> None:
        """Upsert validation results. One row per story_id (latest wins)."""
        if not results:
            return

        rows = []
        for r in results:
            invest_breakdown_json = (
                json.dumps(r.invest_breakdown.model_dump()) if r.invest_breakdown else None
            )
            issues_json = json.dumps([i.model_dump() for i in r.issues])

            rows.append(
                {
                    "id": str(uuid4()),
                    "user_story_id": r.story_id,
                    "status": r.status,
                    "overall_quality_score": r.overall_quality_score,
                    "recommendation": r.recommendation,
                    "semantic_similarity": r.semantic_similarity,
                    "evidence_score": r.evidence_score,
                    "invest_score": r.invest_score,
                    "hallucination_score": r.hallucination_score,
                    "rule_score": r.rule_score,
                    "invest_breakdown": invest_breakdown_json,
                    "issues": issues_json,
                }
            )

        try:
            # Upsert on user_story_id so we always keep the latest result
            self._upsert_validation_rows(rows)
            LOGGER.info("[ValidationRepository] Saved %d validation result(s).", len(rows))
        except Exception as exc:
            LOGGER.error("[ValidationRepository] Failed to save validation results: %s", exc)

    def get_by_story_id(self, story_id: str) -> ValidationResult | None:
        """Fetch the latest validation result for a given story_id."""
        try:
            rows = self._gateway.execute_query(
                f'SELECT * FROM "{self._table}" WHERE user_story_id = %s '
                f"ORDER BY validated_at DESC LIMIT 1",
                (story_id,),
            )
            if not rows:
                return None
            return self._row_to_model(rows[0])
        except Exception as exc:
            LOGGER.error("[ValidationRepository] get_by_story_id failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """Create the table if it does not exist yet."""
        try:
            self._gateway.execute(_CREATE_TABLE_SQL)
        except Exception as exc:
            LOGGER.warning(
                "[ValidationRepository] Could not ensure table existence: %s", exc
            )

    def _upsert_validation_rows(self, rows: list[dict]) -> None:
        """Delete existing validation records for these stories, then insert fresh rows."""
        for row in rows:
            try:
                self._gateway.delete(
                    self._table,
                    eq={"user_story_id": row["user_story_id"]},
                )
            except Exception as exc:
                LOGGER.warning(
                    "[ValidationRepository] Could not delete old record for story %s: %s",
                    row["user_story_id"],
                    exc,
                )

        self._gateway.upsert(self._table, rows, on_conflict="id")

    def _row_to_model(self, row: dict) -> ValidationResult:
        """Convert a raw DB row dict to a ValidationResult model."""
        from src.models.user_story import InvestScore, StoryIssue

        invest_breakdown = None
        if row.get("invest_breakdown"):
            try:
                raw = row["invest_breakdown"]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                invest_breakdown = InvestScore(**raw)
            except Exception:
                pass

        issues: list[StoryIssue] = []
        if row.get("issues"):
            try:
                raw_issues = row["issues"]
                if isinstance(raw_issues, str):
                    raw_issues = json.loads(raw_issues)
                issues = [StoryIssue(**i) for i in raw_issues]
            except Exception:
                pass

        return ValidationResult(
            story_id=str(row.get("user_story_id", "")),
            status=row.get("status", "Needs Review"),
            overall_quality_score=float(row.get("overall_quality_score", 0)),
            recommendation=row.get("recommendation", ""),
            semantic_similarity=float(row.get("semantic_similarity", 0)),
            evidence_score=float(row.get("evidence_score", 0)),
            invest_score=float(row.get("invest_score", 0)),
            hallucination_score=float(row.get("hallucination_score", 0)),
            rule_score=float(row.get("rule_score", 100)),
            invest_breakdown=invest_breakdown,
            issues=issues,
        )
