"""Supabase integration helpers local to text-to-user-stories service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - validated at runtime when enabled
    Client = Any  # type: ignore[misc,assignment]
    create_client = None


@dataclass(frozen=True)
class SupabaseSettings:
    """Environment-driven Supabase configuration for text service."""

    url: str
    service_role_key: str
    schema: str
    speech_schema: str
    transcripts_table: str
    utterances_table: str
    chunks_table: str
    story_runs_table: str
    stories_table: str
    speech_sessions_table: str
    captions_table: str

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.service_role_key)


from src.core.config import Settings

def load_supabase_settings() -> SupabaseSettings:
    s = Settings()
    return SupabaseSettings(
        url=s.supabase_url.strip(),
        service_role_key=s.supabase_key.strip(),
        schema=s.supabase_schema.strip(),
        speech_schema=s.supabase_speech_schema.strip(),
        transcripts_table=s.supabase_transcripts_table.strip(),
        utterances_table=s.supabase_utterances_table.strip(),
        chunks_table=s.supabase_chunks_table.strip(),
        story_runs_table=s.supabase_story_runs_table.strip(),
        stories_table=s.supabase_stories_table.strip(),
        speech_sessions_table=s.supabase_speech_sessions_table.strip(),
        captions_table=s.supabase_captions_table.strip(),
    )


class SupabaseGateway:
    """Thin wrapper over Supabase client with no-op behavior when disabled."""

    def __init__(self, settings: SupabaseSettings) -> None:
        self.settings = settings
        self._client: Client | None = None

        if not settings.enabled:
            return

        if create_client is None:
            raise RuntimeError(
                "Supabase is configured but the 'supabase' package is not installed. "
                "Install it before enabling Supabase persistence."
            )

        self._client = create_client(settings.url, settings.service_role_key)

    @classmethod
    def from_env(cls) -> "SupabaseGateway":
        return cls(load_supabase_settings())

    def upsert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], on_conflict: str | None = None, schema: str | None = None) -> None:
        if not self._client:
            return

        target_schema = schema or self.settings.schema
        query = self._client.schema(target_schema).table(table).upsert(rows)
        if on_conflict:
            query = self._client.schema(target_schema).table(table).upsert(rows, on_conflict=on_conflict)
        query.execute()

    def insert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], schema: str | None = None) -> None:
        if not self._client:
            return

        target_schema = schema or self.settings.schema
        self._client.schema(target_schema).table(table).insert(rows).execute()

    def update(self, table: str, values: dict[str, Any], *, eq: dict[str, Any]) -> None:
        if not self._client:
            return

        query = self._client.schema(self.settings.schema).table(table).update(values)
        for key, value in eq.items():
            query = query.eq(key, value)
        query.execute()