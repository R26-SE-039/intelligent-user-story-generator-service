"""Repository for conflict data."""

from __future__ import annotations

from src.db.postgres import PostgresGateway
from src.models.conflict import Conflict
from src.utils.helpers import utc_now


class ConflictRepository:
    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save(self, conflicts: list[Conflict]) -> None:
        if not conflicts:
            return

        rows = []
        for conflict in conflicts:
            rows.append(
                {
                    "id": conflict.conflict_id,
                    "requirement_a_id": conflict.requirement_a_id,
                    "requirement_b_id": conflict.requirement_b_id,
                    "source_meeting_id": conflict.source_meeting_id,
                    "conflict_type": conflict.conflict_type,
                    "severity": conflict.severity,
                    "explanation": conflict.explanation,
                    "status": conflict.status or "active",
                    "suggested_resolution": conflict.suggested_resolution,
                    "resolved_by": conflict.resolved_by,
                    "resolved_at": conflict.resolved_at,
                }
            )
        self._gateway.upsert(self._gateway.settings.conflicts_table, rows, on_conflict="id")

    def get_by_meeting(self, meeting_id: str, status: str | None = "active") -> list[dict]:
        """Fetch conflicts involving requirements from a meeting, defaulting to active conflicts."""
        conflicts_table = self._gateway.settings.conflicts_table
        req_table = self._gateway.settings.requirements_table
        meetings_table = self._gateway.settings.meetings_table

        status_clause = ""
        params: list = [meeting_id]
        if status:
            status_clause = 'AND c."status" = %s'
            params.append(status)

        query = f"""
            SELECT 
                c.*,
                ra."requirement_text" AS requirement_a_text,
                ra."requirement_type" AS requirement_a_type,
                rb."requirement_text" AS requirement_b_text,
                rb."requirement_type" AS requirement_b_type,
                mb."title" AS source_meeting_title
            FROM "{conflicts_table}" c
            JOIN "{req_table}" ra ON ra."id" = c."requirement_a_id"
            JOIN "{req_table}" rb ON rb."id" = c."requirement_b_id"
            LEFT JOIN "{meetings_table}" mb ON mb."id" = rb."meeting_id"
            WHERE ra."meeting_id" = %s {status_clause} AND c."conflict_type" != 'duplicate'
            ORDER BY c."id" ASC
        """
        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def get_by_project(self, project_id: str, status: str | None = "active") -> list[dict]:
        """Fetch conflicts across all meetings in a project."""
        conflicts_table = self._gateway.settings.conflicts_table
        req_table = self._gateway.settings.requirements_table
        meetings_table = self._gateway.settings.meetings_table

        status_clause = ""
        params: list = [project_id]
        if status:
            status_clause = 'AND c."status" = %s'
            params.append(status)

        query = f"""
            SELECT 
                c.*,
                ra."requirement_text" AS requirement_a_text,
                ra."requirement_type" AS requirement_a_type,
                rb."requirement_text" AS requirement_b_text,
                rb."requirement_type" AS requirement_b_type,
                mb."title" AS source_meeting_title
            FROM "{conflicts_table}" c
            JOIN "{req_table}" ra ON ra."id" = c."requirement_a_id"
            JOIN "{req_table}" rb ON rb."id" = c."requirement_b_id"
            LEFT JOIN "{meetings_table}" mb ON mb."id" = rb."meeting_id"
            WHERE mb."project_id" = %s {status_clause} AND c."conflict_type" != 'duplicate'
            ORDER BY c."id" ASC
        """
        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def get_by_id(self, conflict_id: str) -> dict | None:
        """Fetch single conflict by ID."""
        rows = self._gateway.select(self._gateway.settings.conflicts_table, eq={"id": conflict_id})
        return rows[0] if rows else None

    def resolve_conflict(
        self,
        conflict_id: str,
        resolved_by: str | None = None,
        previous_text_a: str | None = None,
        previous_text_b: str | None = None,
    ) -> None:
        """Mark conflict status as resolved and log audit information."""
        self._gateway.update(
            self._gateway.settings.conflicts_table,
            {
                "status": "resolved",
                "resolved_by": resolved_by,
                "resolved_at": utc_now(),
                "previous_text_a": previous_text_a,
                "previous_text_b": previous_text_b,
            },
            eq={"id": conflict_id},
        )

    def delete_conflict(self, conflict_id: str) -> None:
        """Remove a resolved conflict entry by ID."""
        self._gateway.delete(
            self._gateway.settings.conflicts_table,
            eq={"id": conflict_id}
        )
