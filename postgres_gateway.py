"""PostgreSQL gateway for the unified user story generator service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
except ImportError:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None
    execute_values = None

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None


@dataclass(frozen=True)
class PostgresSettings:
    """Environment-driven PostgreSQL configuration."""

    host: str
    port: int
    user: str
    password: str
    dbname: str
    
    meetings_table: str
    chat_messages_table: str
    transcripts_table: str
    transcript_utterances_table: str
    requirements_table: str
    requirement_embeddings_table: str
    requirement_utterance_mapping_table: str
    conflicts_table: str
    user_stories_table: str
    user_story_requirement_mapping_table: str
    acceptance_criteria_table: str

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.user and self.dbname)


from src.core.config import Settings

def load_postgres_settings() -> PostgresSettings:
    s = Settings()
    return PostgresSettings(
        host=s.db_host.strip(),
        port=s.db_port,
        user=s.db_user.strip(),
        password=s.db_password.strip(),
        dbname=s.db_name.strip(),
        meetings_table=s.meetings_table.strip(),
        chat_messages_table=s.chat_messages_table.strip(),
        transcripts_table=s.transcripts_table.strip(),
        transcript_utterances_table=s.transcript_utterances_table.strip(),
        requirements_table=s.requirements_table.strip(),
        requirement_embeddings_table=s.requirement_embeddings_table.strip(),
        requirement_utterance_mapping_table=s.requirement_utterance_mapping_table.strip(),
        conflicts_table=s.conflicts_table.strip(),
        user_stories_table=s.user_stories_table.strip(),
        user_story_requirement_mapping_table=s.user_story_requirement_mapping_table.strip(),
        acceptance_criteria_table=s.acceptance_criteria_table.strip(),
    )


class PostgresGateway:
    """Wrapper over psycopg2 mimicking the previous Supabase client interface."""

    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings
        self._conn_kwargs = {
            "host": settings.host,
            "port": settings.port,
            "user": settings.user,
            "password": settings.password,
            "dbname": settings.dbname,
        }

        if not settings.enabled:
            return

        if psycopg2 is None:
            raise RuntimeError(
                "PostgreSQL is configured but the 'psycopg2-binary' package is not installed."
            )

    @classmethod
    def from_env(cls) -> "PostgresGateway":
        return cls(load_postgres_settings())

    def _get_connection(self):
        return psycopg2.connect(**self._conn_kwargs)

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

    def get_user(self, token: str, secret: str) -> dict[str, Any] | None:
        if jwt is None:
            raise RuntimeError(
                "PyJWT is required for authentication. Install it with: pip install PyJWT"
            )
        try:
            decoded = jwt.decode(token, secret, algorithms=["HS256"])
            if not decoded.get("sub"):
                return None

            return {
                "id": decoded["sub"],
                "email": decoded.get("email", "unknown@example.com"),
                "role": decoded.get("role", "user"),
            }
        except Exception as e:
            print(f"Auth error: {e}")
            return None
