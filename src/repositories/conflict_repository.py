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
