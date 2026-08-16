"""Repository for managing requirement_threads in PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from src.db.postgres import PostgresGateway

LOGGER = logging.getLogger(__name__)


class ThreadRepository:
    """PostgreSQL data access layer for requirement_threads."""

    def __init__(self, gateway: PostgresGateway) -> None:
        self.gateway = gateway
        self.table_name = "requirement_threads"

    def create_thread(
        self,
        meeting_id: str,
        title: str,
        summary: str,
        state: str = "DISCOVERED",
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Create and store a new requirement thread."""
        thread_id = str(uuid4())
        data = {
            "id": thread_id,
            "meeting_id": meeting_id,
            "requirement_title": title,
            "summary": summary,
            "state": state,
        }
        self.gateway.insert(self.table_name, data)

        if embedding:
            self.update_thread_embedding(thread_id, embedding)

        return self.get_thread(thread_id) or data

    def update_thread_embedding(self, thread_id: str, embedding: list[float]) -> None:
        """Update pgvector embedding column for a thread."""
        if not embedding or len(embedding) != 3072:
            LOGGER.warning("[ThreadRepository] Vector embedding length must be 3072 (got %s)", len(embedding) if embedding else 0)
            return

        vector_str = "[" + ",".join(map(str, embedding)) + "]"
        query = f"UPDATE {self.table_name} SET embedding = %s::vector, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        self.gateway.execute(query, (vector_str, thread_id))

    def update_thread_state(
        self,
        thread_id: str,
        state: str,
        summary: str | None = None,
    ) -> None:
        """Update the lifecycle state and optionally summary of a thread."""
        updates: dict[str, Any] = {"state": state}
        if summary:
            updates["summary"] = summary

        query = f"UPDATE {self.table_name} SET state = %s, updated_at = CURRENT_TIMESTAMP"
        params = [state]
        if summary:
            query += ", summary = %s"
            params.append(summary)
        query += " WHERE id = %s"
        params.append(thread_id)

        self.gateway.execute(query, tuple(params))

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Retrieve a thread by ID."""
        rows = self.gateway.select(self.table_name, eq={"id": thread_id})
        return rows[0] if rows else None

    def get_threads_by_meeting(self, meeting_id: str) -> list[dict[str, Any]]:
        """Retrieve all threads for a specific meeting."""
        return self.gateway.select(
            self.table_name,
            eq={"meeting_id": meeting_id},
        )

    def find_similar_threads(
        self,
        meeting_id: str,
        embedding: list[float],
        distance_threshold: float = 0.45,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Find existing threads in the same meeting similar to the given embedding using pgvector cosine distance."""
        if not embedding or len(embedding) != 3072:
            return []

        vector_str = "[" + ",".join(map(str, embedding)) + "]"
        query = f"""
            SELECT id, meeting_id, requirement_title, summary, state,
                   (embedding <=> %s::vector) AS distance
            FROM {self.table_name}
            WHERE meeting_id = %s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s
        """
        params = (vector_str, meeting_id, vector_str, limit)
        rows = self.gateway.execute_query(query, params)

        similar = []
        for r in rows:
            dist = float(r.get("distance", 1.0))
            if dist <= distance_threshold:
                r["similarity_score"] = round(1.0 - dist, 4)
                similar.append(r)

        return similar

    def link_requirement_to_thread(self, requirement_id: str, thread_id: str) -> None:
        """Link a requirement to a thread in the requirements table."""
        self.gateway.update(
            "requirements",
            {"thread_id": thread_id},
            eq={"id": requirement_id},
        )
