"""Repository for conflict data."""

from __future__ import annotations

from src.db.postgres import PostgresGateway
from src.models.conflict import Conflict


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
                    "conflict_type": conflict.conflict_type,
                    "severity": conflict.severity,
                    "explanation": conflict.explanation
                }
            )
        self._gateway.upsert(self._gateway.settings.conflicts_table, rows, on_conflict="id")

    def get_by_meeting(self, meeting_id: str) -> list[dict]:
        """Fetch all conflicts involving requirements from a meeting."""
        conflicts_table = self._gateway.settings.conflicts_table
        req_table = self._gateway.settings.requirements_table
        
        query = f"""
            SELECT c.*
            FROM "{conflicts_table}" c
            JOIN "{req_table}" r ON r."id" = c."requirement_a_id"
            WHERE r."meeting_id" = %s
        """
        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (meeting_id,))
                return [dict(row) for row in cur.fetchall()]

