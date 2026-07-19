"""Requirement Thread Manager Service.

Groups incoming requirement extractions into unified requirement threads,
maintains lifecycle state machines (DISCOVERED -> DISCUSSION -> REFINED -> VALIDATED),
and utilizes Gemini semantic embeddings in PostgreSQL pgvector memory.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

from src.core.config import Settings
from src.core.llm import get_llm_client
from src.db.postgres import PostgresGateway
from src.repositories.thread_repository import ThreadRepository

LOGGER = logging.getLogger(__name__)


class RequirementState(str, Enum):
    """Lifecycle states for a requirement thread."""
    DISCOVERED = "DISCOVERED"
    DISCUSSION = "DISCUSSION"
    REFINED = "REFINED"
    VALIDATED = "VALIDATED"


class RequirementThreadService:
    """Manager service for requirement thread grouping and state machine management."""

    def __init__(self, gateway: PostgresGateway | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.gateway = gateway or PostgresGateway.from_env()
        self.thread_repo = ThreadRepository(self.gateway)
        self.genai_client = get_llm_client(self.settings)

    def _evaluate_transition(self, current_summary: str, current_state: str, new_text: str) -> tuple[str, str]:
        """Use Gemini LLM to analyze how new text influences the thread summary and state."""
        lower = new_text.lower()
        is_confirmation_keywords = any(w in lower for w in ["yes", "agree", "confirm", "finalized", "approved", "agreed"])

        if self.genai_client is not None:
            prompt = f"""You are a Product Owner assistant analyzing an agile requirement thread.
Current Thread Summary: "{current_summary}"
Current Thread State: "{current_state}"
New Utterance/Requirement: "{new_text}"

Tasks:
1. Determine the updated thread state from: ["DISCOVERED", "DISCUSSION", "REFINED", "VALIDATED"].
   - Choose "VALIDATED" if the user confirms, agrees, approves, or finalizes the requirement.
   - Choose "REFINED" if new details, conditions, or scope clarifications are added.
   - Choose "DISCUSSION" if general discussion or elaboration occurs.
2. Provide an updated single-sentence thread summary combining the current summary and new input.

Return ONLY a JSON object:
{{
  "state": "VALIDATED",
  "updated_summary": "Short combined summary"
}}
"""
            try:
                model_name = getattr(self.settings, "chat_model", "gemini-3.1-flash-lite")
                res = self.genai_client.interactions.create(
                    model=model_name,
                    input=prompt,
                    response_format={"type": "text", "mime_type": "application/json"}
                )
                content = res.output_text.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()

                data = json.loads(content)
                new_state = data.get("state", current_state)
                updated_summary = data.get("updated_summary", f"{current_summary} | {new_text}")
                return new_state, updated_summary
            except Exception as e:
                LOGGER.warning("[RequirementThreadService] LLM Transition analysis error: %s", e)

        if is_confirmation_keywords:
            return RequirementState.VALIDATED.value, f"{current_summary} | Confirmed: {new_text}"
        return RequirementState.DISCUSSION.value, f"{current_summary} | {new_text}"

    def process_requirement(
        self,
        meeting_id: str,
        requirement_id: str,
        requirement_text: str,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Group requirement into a thread and update lifecycle state.

        Args:
            meeting_id: Meeting ID context.
            requirement_id: ID of the requirement.
            requirement_text: The text of the requirement.
            embedding: 3072-dimensional vector embedding.

        Returns:
            Dict representing the associated thread data.
        """
        if not requirement_text:
            return {}

        # 1. Search for existing similar thread in the same meeting using pgvector
        similar_threads = []
        if embedding:
            similar_threads = self.thread_repo.find_similar_threads(
                meeting_id=meeting_id,
                embedding=embedding,
                distance_threshold=0.45,
                limit=1,
            )

        if similar_threads:
            # Match found! Merge into existing thread
            target_thread = similar_threads[0]
            thread_id = target_thread["id"]
            current_state = target_thread.get("state", RequirementState.DISCOVERED.value)
            current_summary = target_thread.get("summary", target_thread.get("requirement_title", ""))

            # Evaluate state transition
            new_state, new_summary = self._evaluate_transition(
                current_summary=current_summary,
                current_state=current_state,
                new_text=requirement_text,
            )

            # Update thread state & summary
            self.thread_repo.update_thread_state(
                thread_id=thread_id,
                state=new_state,
                summary=new_summary,
            )
            if embedding:
                self.thread_repo.update_thread_embedding(thread_id, embedding)

            # Link requirement to existing thread
            self.thread_repo.link_requirement_to_thread(requirement_id, thread_id)

            LOGGER.info(
                "[RequirementThreadService] Requirement '%s...' matched existing thread %s. State transition: %s -> %s",
                requirement_text[:40],
                thread_id,
                current_state,
                new_state,
            )
            return self.thread_repo.get_thread(thread_id) or target_thread

        else:
            # No matching thread -> Create a new thread in DISCOVERED state
            title = requirement_text[:120]
            new_thread = self.thread_repo.create_thread(
                meeting_id=meeting_id,
                title=title,
                summary=requirement_text,
                state=RequirementState.DISCOVERED.value,
                embedding=embedding,
            )
            thread_id = new_thread["id"]

            # Link requirement to new thread
            self.thread_repo.link_requirement_to_thread(requirement_id, thread_id)

            LOGGER.info(
                "[RequirementThreadService] Created new thread %s ('%s...') in state DISCOVERED",
                thread_id,
                title[:40],
            )
            return new_thread
