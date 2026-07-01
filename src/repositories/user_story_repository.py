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
        self._gateway.upsert(self._gateway.settings.user_story_requirement_mapping_table, mappings, on_conflict="user_story_id")
