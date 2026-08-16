"""PostgreSQL gateway for the unified user story generator service."""

from __future__ import annotations

import json
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
except ImportError:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None
    execute_values = None

from src.core.config import PostgresSettings, load_postgres_settings
from src.db.connection import get_connection

class PostgresGateway:
    """Wrapper over psycopg2 for executing DB operations."""

    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings
        
        if not settings.enabled:
            return

        if psycopg2 is None:
            raise RuntimeError(
                "PostgreSQL is configured but the 'psycopg2-binary' package is not installed."
            )

        try:
            self.run_migrations()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[PostgresGateway] Migration warning: {e}")

    @classmethod
    def from_env(cls) -> "PostgresGateway":
        return cls(load_postgres_settings())

    def run_migrations(self) -> None:
        """Run idempotent database migrations to ensure required schema columns exist."""
        migrations = [
            """
            ALTER TABLE meetings 
                ADD COLUMN IF NOT EXISTS iteration_id UUID;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_meetings_iteration_id ON meetings(iteration_id);
            """,
            """
            ALTER TABLE conflicts 
                ADD COLUMN IF NOT EXISTS source_meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'active',
                ADD COLUMN IF NOT EXISTS suggested_resolution TEXT,
                ADD COLUMN IF NOT EXISTS previous_text_a TEXT,
                ADD COLUMN IF NOT EXISTS previous_text_b TEXT,
                ADD COLUMN IF NOT EXISTS resolved_by UUID,
                ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;
            """,
            """
            ALTER TABLE requirements 
                ADD COLUMN IF NOT EXISTS duplicate_of_id UUID REFERENCES requirements(id) ON DELETE SET NULL;
            """
        ]
        
        import logging
        logger = logging.getLogger(__name__)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for sql in migrations:
                    try:
                        cur.execute(sql)
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        logger.warning(f"[PostgresGateway] Migration statement failed: {e}")


    def _get_connection(self):
        return get_connection(self.settings)

    def _format_value(self, val: Any) -> Any:
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return val

    def upsert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], on_conflict: str | None = None, schema: str | None = None) -> None:
        if not rows:
            return
            
        if isinstance(rows, dict):
            rows = [rows]

        columns = list(rows[0].keys())
        
        # Prepare values for execute_values
        values_list = []
        for row in rows:
            values_list.append(tuple(self._format_value(row.get(c)) for c in columns))

        col_str = ", ".join([f'"{c}"' for c in columns])
        
        target = f'"{table}"'
        if schema:
            target = f'"{schema}"."{table}"'

        query = f"INSERT INTO {target} ({col_str}) VALUES %s"
        
        if on_conflict:
            update_str = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in columns if c != on_conflict])
            if update_str:
                query += f' ON CONFLICT ("{on_conflict}") DO UPDATE SET {update_str}'
            else:
                query += f' ON CONFLICT ("{on_conflict}") DO NOTHING'

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, values_list)
            conn.commit()

    def insert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], schema: str | None = None) -> None:
        if not rows:
            return
            
        if isinstance(rows, dict):
            rows = [rows]

        columns = list(rows[0].keys())
        values_list = []
        for row in rows:
            values_list.append(tuple(self._format_value(row.get(c)) for c in columns))

        col_str = ", ".join([f'"{c}"' for c in columns])
        
        target = f'"{table}"'
        if schema:
            target = f'"{schema}"."{table}"'

        query = f"INSERT INTO {target} ({col_str}) VALUES %s"

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, query, values_list)
            conn.commit()

    def update(self, table: str, values: dict[str, Any], *, eq: dict[str, Any], schema: str | None = None) -> None:
        if not values or not eq:
            return

        target = f'"{table}"'
        if schema:
            target = f'"{schema}"."{table}"'

        set_clauses = []
        query_vals = []
        for k, v in values.items():
            set_clauses.append(f'"{k}" = %s')
            query_vals.append(self._format_value(v))
            
        where_clauses = []
        for k, v in eq.items():
            where_clauses.append(f'"{k}" = %s')
            query_vals.append(v)

        query = f"UPDATE {target} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(query_vals))
            conn.commit()

    def delete(self, table: str, *, eq: dict[str, Any], schema: str | None = None) -> None:
        if not eq:
            return

        target = f'"{table}"'
        if schema:
            target = f'"{schema}"."{table}"'

        where_clauses = []
        query_vals = []
        for k, v in eq.items():
            where_clauses.append(f'"{k}" = %s')
            query_vals.append(v)

        query = f"DELETE FROM {target} WHERE {' AND '.join(where_clauses)}"

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(query_vals))
            conn.commit()

    def select(self, table: str, *, eq: dict[str, Any] | None = None, schema: str | None = None) -> list[dict[str, Any]]:
        target = f'"{table}"'
        if schema:
            target = f'"{schema}"."{table}"'

        query = f"SELECT * FROM {target}"
        query_vals = []

        if eq:
            where_clauses = []
            for k, v in eq.items():
                where_clauses.append(f'"{k}" = %s')
                query_vals.append(v)
            query += f" WHERE {' AND '.join(where_clauses)}"

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, tuple(query_vals))
                rows = cur.fetchall()
                # RealDictRow behaves mostly like a dict
                return [dict(row) for row in rows]

    def execute(self, query: str, params: tuple | list | None = None) -> None:
        """Execute a raw SQL command (e.g. UPDATE, INSERT, ALTER)."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
            conn.commit()

    def execute_query(self, query: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
        """Execute a raw SELECT query and return rows as dictionary list."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or ())
                rows = cur.fetchall()
                return [dict(row) for row in rows]
