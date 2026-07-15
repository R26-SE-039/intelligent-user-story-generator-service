"""Repository for user story data."""

from __future__ import annotations
from uuid import uuid4

from src.db.postgres import PostgresGateway
from src.models.user_story import GeneratedStory


class UserStoryRepository:
    def __init__(self, gateway: PostgresGateway) -> None:
        self._gateway = gateway

    def save(self, stories: list[GeneratedStory], meeting_id: str | None = None) -> None:
        if not stories:
            return

        story_rows = []
        ac_rows = []
        
        for story in stories:
            try:
                import uuid
                uuid.UUID(story.story_id)
            except ValueError:
                story.story_id = str(uuid4())
            story_id = story.story_id
            story_rows.append(
                {
                    "id": story_id,
                    "meeting_id": meeting_id,
                    "title": story.title,
                    "story": story.story,
                    "priority": story.priority,
                    "status": story.status,
                }
            )
            
            for ac in story.acceptance_criteria:
                ac_rows.append(
                    {
                        "id": str(uuid4()),
                        "user_story_id": story_id,
                        "criteria": ac
                    }
                )

        self._gateway.upsert(self._gateway.settings.user_stories_table, story_rows, on_conflict="id")
        self._gateway.upsert(self._gateway.settings.acceptance_criteria_table, ac_rows, on_conflict="id")

    def save_requirement_mappings(self, mappings: list[dict[str, str]]) -> None:
        if not mappings:
            return
        table = self._gateway.settings.user_story_requirement_mapping_table
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

