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
            # story.story_id is guaranteed to be a valid UUID by the model field_validator
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
                        "criteria": ac,
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

    def update_story(
        self,
        story_id: str,
        title: str,
        story: str,
        acceptance_criteria: list[str],
        priority: str = "Should",
    ) -> None:
        """Update story text and replace acceptance criteria rows for a story."""
        # 1. Update user_stories table
        self._gateway.update(
            self._gateway.settings.user_stories_table,
            {
                "title": title,
                "story": story,
                "priority": priority,
            },
            eq={"id": story_id},
        )

        # 2. Refresh acceptance_criteria rows
        try:
            self._gateway.delete(
                self._gateway.settings.acceptance_criteria_table,
                eq={"user_story_id": story_id},
            )
        except Exception:
            pass

        ac_rows = [
            {
                "id": str(uuid4()),
                "user_story_id": story_id,
                "criteria": ac,
            }
            for ac in acceptance_criteria
            if ac.strip()
        ]
        if ac_rows:
            self._gateway.upsert(
                self._gateway.settings.acceptance_criteria_table,
                ac_rows,
                on_conflict="id",
            )

    def get_by_id(self, story_id: str) -> dict | None:
        """Fetch user story row with acceptance criteria."""
        stories = self._gateway.select(
            self._gateway.settings.user_stories_table,
            eq={"id": story_id},
        )
        if not stories:
            return None
        story_row = dict(stories[0])
        ac_rows = self._gateway.select(
            self._gateway.settings.acceptance_criteria_table,
            eq={"user_story_id": story_id},
        )
        story_row["acceptance_criteria"] = [r["criteria"] for r in ac_rows if r.get("criteria")]
        return story_row

