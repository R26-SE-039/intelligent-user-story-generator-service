"""Repository for requirement data."""

from __future__ import annotations

from src.db.postgres import PostgresGateway
from src.models.requirement import Requirement
from src.utils.helpers import utc_now

try:
    from psycopg2.extras import execute_values, RealDictCursor
except ImportError:
    execute_values = None
    RealDictCursor = None


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

    def save_embeddings(self, embeddings_data: list[dict[str, any]]) -> None:
        if not embeddings_data:
            return
            
        rows = []
        for data in embeddings_data:
            # Format vector as string for pgvector insertion e.g. '[0.1, 0.2, ...]'
            vec_str = "[" + ",".join(str(x) for x in data["embedding"]) + "]"
            rows.append({
                "requirement_id": data["requirement_id"],
                "embedding": vec_str
            })
            
        self._gateway.upsert(self._gateway.settings.requirement_embeddings_table, rows, on_conflict="requirement_id")

    def save_utterance_mappings(self, mappings: list[dict[str, str]]) -> None:
        if not mappings:
            return
        
        # We need to manually construct the upsert for composite primary key
        # since our helper upsert assumes a single column on_conflict.
        # But wait, requirement_utterance_mapping table has no other columns to update
        # on conflict! We can just use 'insert ... ON CONFLICT DO NOTHING'
        table = self._gateway.settings.requirement_utterance_mapping_table
        
        columns = list(mappings[0].keys())
        values_list = []
        for m in mappings:
            values_list.append(tuple(self._gateway._format_value(m.get(c)) for c in columns))
            
        col_str = ", ".join([f'"{c}"' for c in columns])
        query = f'INSERT INTO "{table}" ({col_str}) VALUES %s ON CONFLICT DO NOTHING'
        
        from psycopg2.extras import execute_values
        with self._gateway._get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, values_list)
            conn.commit()

    def get_by_meeting(self, meeting_id: str, status: str = "active") -> list[dict]:
        """Fetch all requirements for a meeting with a given status."""
        req_table = self._gateway.settings.requirements_table
        query = f'SELECT * FROM "{req_table}" WHERE "meeting_id" = %s AND "status" = %s'
        
        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (meeting_id, status))
                return [dict(row) for row in cur.fetchall()]

    def update_status(self, requirement_id: str, status: str) -> None:
        """Update the status of a requirement (e.g., 'conflicted', 'superseded', 'duplicate')."""
        self._gateway.update(
            self._gateway.settings.requirements_table,
            {"status": status},
            eq={"id": requirement_id}
        )

    def update_status_by_thread(self, thread_id: str, status: str) -> None:
        """Update the status of all requirements belonging to a thread."""
        self._gateway.update(
            self._gateway.settings.requirements_table,
            {"status": status},
            eq={"thread_id": thread_id}
        )

    def update_active_status_by_thread(self, thread_id: str, status: str) -> None:
        """Update status of requirements in a thread ONLY if their status is not superseded, duplicate, or discarded."""
        req_table = self._gateway.settings.requirements_table
        query = f'UPDATE "{req_table}" SET "status" = %s WHERE "thread_id" = %s AND "status" NOT IN (\'superseded\', \'duplicate\', \'discarded\')'
        with self._gateway._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (status, thread_id))
            conn.commit()

    def update_text(self, requirement_id: str, text: str) -> None:
        """Update requirement_text for a requirement."""
        self._gateway.update(
            self._gateway.settings.requirements_table,
            {"requirement_text": text},
            eq={"id": requirement_id}
        )

    def update_thread_id(self, requirement_id: str, thread_id: str) -> None:
        """Set thread_id for a requirement."""
        self._gateway.update(
            self._gateway.settings.requirements_table,
            {"thread_id": thread_id},
            eq={"id": requirement_id}
        )

    def find_similar_by_embedding(
        self, embedding: list[float], meeting_id: str, top_k: int = 10, exclude_id: str | None = None
    ) -> list[dict]:
        """
        Use pgvector cosine similarity (<=> operator) to find the most semantically
        similar requirements in the same meeting — regardless of status.
        This ensures every new requirement is checked against ALL prior ones
        (active AND conflicted) so no conflict pair is missed.
        Returns rows with id, requirement_text, requirement_type, status, distance.
        """
        req_table = self._gateway.settings.requirements_table
        emb_table = self._gateway.settings.requirement_embeddings_table
        
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        
        exclude_clause = ""
        params: list = [vec_str, meeting_id]
        if exclude_id:
            exclude_clause = 'AND r."id" != %s'
            params.append(exclude_id)
        params.append(top_k)
        
        # NOTE: No status filter — we check the new requirement against ALL
        # previous requirements in the meeting (active, conflicted, etc.).
        # This prevents missing conflicts where one side was already flagged.
        query = f"""
            SELECT r."id", r."meeting_id", r."requirement_text", r."requirement_type", r."status",
                   (re."embedding" <=> %s::vector) AS distance
            FROM "{emb_table}" re
            JOIN "{req_table}" r ON r."id" = re."requirement_id"
            WHERE r."meeting_id" = %s
            {exclude_clause}
            ORDER BY distance ASC
            LIMIT %s;
        """
        
        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def find_similar_by_project(
        self, embedding: list[float], project_id: str, top_k: int = 10, exclude_id: str | None = None
    ) -> list[dict]:
        """Use pgvector cosine similarity to find similar requirements across all meetings in a project."""
        req_table = self._gateway.settings.requirements_table
        emb_table = self._gateway.settings.requirement_embeddings_table
        meetings_table = self._gateway.settings.meetings_table

        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

        exclude_clause = ""
        params: list = [vec_str, project_id]
        if exclude_id:
            exclude_clause = 'AND r."id" != %s'
            params.append(exclude_id)
        params.append(top_k)

        query = f"""
            SELECT r."id", r."meeting_id", r."requirement_text", r."requirement_type", r."status",
                   m."title" AS meeting_title,
                   (re."embedding" <=> %s::vector) AS distance
            FROM "{emb_table}" re
            JOIN "{req_table}" r ON r."id" = re."requirement_id"
            JOIN "{meetings_table}" m ON m."id" = r."meeting_id"
            WHERE m."project_id" = %s
            {exclude_clause}
            ORDER BY distance ASC
            LIMIT %s;
        """

        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def get_all_for_conflict_check(
        self, meeting_id: str, exclude_id: str | None = None
    ) -> list[dict]:
        """
        Fetch ALL requirements for a meeting (regardless of status) for LLM-based
        conflict checking. Excludes the new requirement itself by ID.
        """
        req_table = self._gateway.settings.requirements_table

        exclude_clause = ""
        params: list = [meeting_id]
        if exclude_id:
            exclude_clause = 'AND "id" != %s'
            params.append(exclude_id)

        query = f"""
            SELECT "id", "meeting_id", "requirement_text", "requirement_type", "status", "duplicate_of_id"
            FROM "{req_table}"
            WHERE "meeting_id" = %s
            {exclude_clause}
            ORDER BY "created_at" ASC;
        """

        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def get_all_by_project_for_conflict_check(
        self, project_id: str, exclude_id: str | None = None
    ) -> list[dict]:
        """Fetch ALL requirements across all meetings in a project for cross-meeting conflict detection."""
        req_table = self._gateway.settings.requirements_table
        meetings_table = self._gateway.settings.meetings_table

        exclude_clause = ""
        params: list = [project_id]
        if exclude_id:
            exclude_clause = 'AND r."id" != %s'
            params.append(exclude_id)

        query = f"""
            SELECT r."id", r."meeting_id", r."requirement_text", r."requirement_type", r."status", m."title" AS meeting_title
            FROM "{req_table}" r
            JOIN "{meetings_table}" m ON m."id" = r."meeting_id"
            WHERE m."project_id" = %s
            {exclude_clause}
            ORDER BY r."created_at" ASC;
        """

        from psycopg2.extras import RealDictCursor
        with self._gateway._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def update_text_and_reembed(
        self, requirement_id: str, new_text: str, embedding: list[float] | None = None
    ) -> None:
        """Update requirement_text, mark status active, and save/upsert new embedding vector."""
        # 1. Update text & status
        self._gateway.update(
            self._gateway.settings.requirements_table,
            {"requirement_text": new_text, "status": "active"},
            eq={"id": requirement_id}
        )

        # 2. Re-embed vector into requirement_embeddings
        if embedding:
            self.save_embeddings([{"requirement_id": requirement_id, "embedding": embedding}])

    def mark_as_duplicate(self, requirement_id: str, duplicate_of_id: str) -> None:
        """Mark a requirement as a duplicate of another requirement."""
        self._gateway.update(
            self._gateway.settings.requirements_table,
            {"status": "duplicate", "duplicate_of_id": duplicate_of_id},
            eq={"id": requirement_id}
        )

