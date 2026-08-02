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
    """Manager service for requirement thread grouping, state machine management, and BA conflict resolutions."""

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
        """Group requirement into a thread and update lifecycle state."""
        if not requirement_text:
            return {}

        # 1. Search for existing similar thread in the same meeting using pgvector
        similar_threads = []
        if embedding:
            similar_threads = self.thread_repo.find_similar_threads(
                meeting_id=meeting_id,
                embedding=embedding,
                distance_threshold=0.30,
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

    def resolve_single_conflict(
        self,
        conflict_id: str,
        resolution_type: str,
        req_repo: Any,
        conflict_repo: Any,
        req_extractor: Any = None,
        edited_text_a: str | None = None,
        edited_text_b: str | None = None,
        merged_text: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute BA Conflict Resolution:
          1. Target requirement text & status update.
          2. Vector re-embedding (Gemini embedding + pgvector upsert).
          3. Competing requirement status update (superseded / discarded / duplicate).
          4. Conflict record audit trail update (status='resolved', resolved_by, resolved_at).
        """
        conflict = conflict_repo.get_by_id(conflict_id)
        if not conflict:
            raise ValueError(f"Conflict with ID {conflict_id} not found")

        req_a_id = str(conflict["requirement_a_id"])
        req_b_id = str(conflict["requirement_b_id"])

        # Fetch original texts for audit trail
        reqs = self.gateway.select(self.gateway.settings.requirements_table, eq={"id": req_a_id})
        prev_a = reqs[0].get("requirement_text", "") if reqs else ""
        reqs_b = self.gateway.select(self.gateway.settings.requirements_table, eq={"id": req_b_id})
        prev_b = reqs_b[0].get("requirement_text", "") if reqs_b else ""

        if resolution_type == "apply_suggestion":
            target_text = conflict.get("suggested_resolution") or merged_text or edited_text_a or prev_a
            new_embedding = req_extractor.get_embedding(target_text) if req_extractor else None
            req_repo.update_text_and_reembed(req_a_id, target_text, new_embedding)
            req_repo.update_status(req_b_id, "superseded")

        elif resolution_type == "keep_a":
            req_repo.update_status(req_a_id, "active")
            req_repo.update_status(req_b_id, "superseded")

        elif resolution_type == "keep_b":
            req_repo.update_status(req_b_id, "active")
            req_repo.update_status(req_a_id, "superseded")

        elif resolution_type == "edit_a":
            target_text = edited_text_a or prev_a
            new_embedding = req_extractor.get_embedding(target_text) if req_extractor else None
            req_repo.update_text_and_reembed(req_a_id, target_text, new_embedding)
            req_repo.update_status(req_b_id, "superseded")

        elif resolution_type == "edit_b":
            target_text = edited_text_b or prev_b
            new_embedding = req_extractor.get_embedding(target_text) if req_extractor else None
            req_repo.update_text_and_reembed(req_b_id, target_text, new_embedding)
            req_repo.update_status(req_a_id, "superseded")

        elif resolution_type == "merge":
            target_text = merged_text or conflict.get("suggested_resolution") or prev_a
            new_embedding = req_extractor.get_embedding(target_text) if req_extractor else None
            req_repo.update_text_and_reembed(req_a_id, target_text, new_embedding)
            req_repo.update_status(req_b_id, "superseded")

        elif resolution_type == "accept_duplicate":
            req_repo.update_status(req_a_id, "active")
            req_repo.mark_as_duplicate(req_b_id, duplicate_of_id=req_a_id)

        elif resolution_type == "dismiss":
            req_repo.update_status(req_a_id, "active")
            req_repo.update_status(req_b_id, "active")

        else:
            raise ValueError(f"Unknown conflict resolution type: '{resolution_type}'")

        # Record audit log in conflicts table
        conflict_repo.resolve_conflict(
            conflict_id=conflict_id,
            resolved_by=user_id,
            previous_text_a=prev_a,
            previous_text_b=prev_b,
        )

        LOGGER.info(
            "[RequirementThreadService] Conflict %s resolved (action: %s) by user %s",
            conflict_id,
            resolution_type,
            user_id,
        )

        return {
            "status": "success",
            "conflict_id": conflict_id,
            "resolution_type": resolution_type,
            "resolved_requirement_a_id": req_a_id,
            "resolved_requirement_b_id": req_b_id,
        }

    def finalize_requirements(
        self,
        meeting_id: str,
        edited_threads: list[Any],
        edited_requirements: list[Any],
        resolutions: list[Any],
        req_repo: Any,
        conflict_repo: Any,
        req_extractor: Any = None,
        user_id: str | None = None,
    ) -> None:
        """Process conflict resolutions, edited requirement threads, inline raw requirement edits, and cleanup."""
        # 1. Process active conflict resolutions FIRST so BA decisions are recorded and applied
        for res in resolutions:
            try:
                self.resolve_single_conflict(
                    conflict_id=res.conflict_id,
                    resolution_type=res.resolution_type,
                    req_repo=req_repo,
                    conflict_repo=conflict_repo,
                    req_extractor=req_extractor,
                    edited_text_a=getattr(res, "edited_text_a", None),
                    edited_text_b=getattr(res, "edited_text_b", None),
                    merged_text=getattr(res, "merged_text", None),
                    user_id=user_id,
                )
            except Exception as exc:
                LOGGER.warning("[RequirementThreadService] Batch conflict resolution failed for %s: %s", res.conflict_id, exc)

        # 2. Process edited requirement threads
        for th in edited_threads:
            thread_id = th.thread_id
            if th.action == "VALIDATED":
                summary_text = th.summary or th.title or "Finalized Requirement"
                self.thread_repo.update_thread_state(thread_id, "VALIDATED", summary=summary_text)

                # Update non-superseded/duplicate/discarded requirements under thread to active
                if hasattr(req_repo, "update_active_status_by_thread"):
                    req_repo.update_active_status_by_thread(thread_id, "active")
                else:
                    req_repo.update_status_by_thread(thread_id, "active")

                # Update in-place the primary active requirement under this thread with summary_text & re-embed vector
                thread_reqs = self.gateway.select(
                    self.gateway.settings.requirements_table,
                    eq={"thread_id": thread_id, "status": "active"}
                )
                if thread_reqs:
                    primary_req_id = str(thread_reqs[0]["id"])
                    new_emb = req_extractor.get_embedding(summary_text) if req_extractor else None
                    req_repo.update_text_and_reembed(primary_req_id, summary_text, new_emb)

            elif th.action == "DISCARDED":
                self.thread_repo.update_thread_state(thread_id, "DISCARDED")
                if hasattr(req_repo, "update_active_status_by_thread"):
                    req_repo.update_active_status_by_thread(thread_id, "discarded")
                else:
                    req_repo.update_status_by_thread(thread_id, "discarded")

        # 3. Update any inline edited raw requirements
        for item in edited_requirements:
            req_repo.update_status(item.requirement_id, "active")
            if req_extractor:
                new_emb = req_extractor.get_embedding(item.text)
                req_repo.update_text_and_reembed(item.requirement_id, item.text, new_emb)
            else:
                req_repo.update_text(item.requirement_id, item.text)

        # 4. Clean up any remaining conflicted requirements that weren't addressed
        remaining = req_repo.get_all_for_conflict_check(meeting_id)
        for req in remaining:
            if req["status"] == "conflicted":
                req_repo.update_status(req["id"], "active")
