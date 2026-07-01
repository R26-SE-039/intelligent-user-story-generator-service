"""Repository for requirement data."""

from __future__ import annotations

from src.db.postgres import PostgresGateway
from src.models.requirement import Requirement
from src.utils.helpers import utc_now


class RequirementRepository:
    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save(self, requirements: list[Requirement]) -> None:
        if not requirements:
            return

        rows = []
        for req in requirements:
            rows.append(
                {
                    "id": req.requirement_id,
                    "meeting_id": req.meeting_id,
                    "requirement_text": req.requirement_text,
                    "requirement_type": req.requirement_type,
                    "status": req.status,
                    "created_at": utc_now(),
                }
            )
        self._gateway.upsert(self._gateway.settings.requirements_table, rows, on_conflict="id")

    def save_embeddings(self, embeddings: list[dict[str, any]]) -> None:
        # Placeholder for pgvector inserts
        pass

    def save_utterance_mappings(self, mappings: list[dict[str, str]]) -> None:
        if not mappings:
            return
        self._gateway.upsert(self._gateway.settings.requirement_utterance_mapping_table, mappings, on_conflict="requirement_id")
