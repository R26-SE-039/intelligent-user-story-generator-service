"""Real-time conflict detection service for requirements."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from uuid import uuid4

from src.core.llm import get_llm_client
from src.core.config import Settings
from src.models.conflict import Conflict
from src.models.requirement import Requirement


# Maximum number of existing requirements to send to the LLM in one call.
# Prevents the context window from becoming too large.
MAX_CANDIDATES = 10


class ConflictDetectorService:
    """
    Detects conflicts between a newly extracted requirement and existing ones
    in the meeting or project using direct LLM-based logical contradiction checking.
    """

    def __init__(self) -> None:
        self.settings = Settings()
        self.client = get_llm_client(self.settings)
        self.model = self.settings.chat_model
        self.prompts_dir = Path(__file__).resolve().parent.parent.parent / "prompts"

    def _load_prompt(self, name: str) -> str:
        return (self.prompts_dir / name).read_text(encoding="utf-8")

    def verify_conflicts_with_llm(
        self, new_req: Requirement, candidates: list[dict]
    ) -> list[Conflict]:
        """
        Ask the LLM to check which of the candidate requirements conflict with
        the new requirement. Returns confirmed Conflict objects with suggested resolutions.
        """
        if not candidates or not self.client:
            return []

        system_prompt = self._load_prompt("conflict_detection_prompt.txt")

        # Format candidate lines with meeting context if cross-meeting
        candidate_lines = []
        for i, c in enumerate(candidates):
            m_ctx = f" [Meeting: {c['meeting_title']}]" if c.get("meeting_title") else ""
            candidate_lines.append(f"{i + 1}. [{c['requirement_type']}]{m_ctx} {c['requirement_text']}")

        user_message = (
            f"NEW REQUIREMENT:\n[{new_req.requirement_type}] {new_req.requirement_text}\n\n"
            f"EXISTING REQUIREMENTS TO CHECK:\n" + "\n".join(candidate_lines)
        )

        try:
            input_text = f"System Instructions:\n{system_prompt}\n\nTask:\n{user_message}"
            interaction = self.client.interactions.create(
                model=self.model,
                input=input_text,
                response_format={
                    "type": "text",
                    "mime_type": "application/json"
                }
            )

            content = interaction.output_text.strip()
            print(f"[ConflictDetector] LLM raw response: {content[:300]}")

            # Extract JSON array substring between first '[' and last ']'
            start_idx = content.find("[")
            end_idx = content.rfind("]")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx : end_idx + 1]
            else:
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                content = content.strip()

            results = json.loads(content)

            conflicts: list[Conflict] = []
            for i, result in enumerate(results):
                if i >= len(candidates):
                    break
                if result.get("conflict"):
                    candidate = candidates[i]
                    source_m_id = candidate.get("meeting_id") if candidate.get("meeting_id") != new_req.meeting_id else None
                    source_title = candidate.get("meeting_title") if source_m_id else None
                    conflicts.append(
                        Conflict(
                            conflict_id=str(uuid4()),
                            requirement_a_id=new_req.requirement_id,
                            requirement_b_id=candidate["id"],
                            conflict_type=result.get("conflict_type", "functional"),
                            severity=result.get("severity", "medium"),
                            explanation=result.get("explanation", ""),
                            source_meeting_id=source_m_id,
                            source_meeting_title=source_title,
                            requirement_a_text=new_req.requirement_text,
                            requirement_b_text=candidate.get("requirement_text"),
                            status="active",
                            suggested_resolution=result.get("suggested_resolution"),
                        )
                    )
            return conflicts

        except Exception as e:
            print(f"[ConflictDetector] LLM verification error: {e}")
            traceback.print_exc()
            return []

    def detect(
        self,
        new_requirement: Requirement,
        req_repository,  # RequirementRepository
        project_id: str | None = None,
        embedding: list[float] | None = None,
    ) -> list[Conflict]:
        """
        Full conflict detection pipeline for one new requirement.
        Supports vector similarity pre-filtering across project or meeting scope.
        """
        try:
            if embedding and any(x != 0.0 for x in embedding):
                if project_id:
                    candidates = req_repository.find_similar_by_project(
                        embedding=embedding,
                        project_id=project_id,
                        top_k=MAX_CANDIDATES,
                        exclude_id=new_requirement.requirement_id,
                    )
                else:
                    candidates = req_repository.find_similar_by_embedding(
                        embedding=embedding,
                        meeting_id=new_requirement.meeting_id,
                        top_k=MAX_CANDIDATES,
                        exclude_id=new_requirement.requirement_id,
                    )
            else:
                if project_id:
                    all_existing = req_repository.get_all_by_project_for_conflict_check(
                        project_id=project_id,
                        exclude_id=new_requirement.requirement_id,
                    )
                else:
                    all_existing = req_repository.get_all_for_conflict_check(
                        meeting_id=new_requirement.meeting_id,
                        exclude_id=new_requirement.requirement_id,
                    )
                candidates = all_existing[:MAX_CANDIDATES]

        except Exception as e:
            print(f"[ConflictDetector] Candidate fetch error: {e}")
            return []

        if not candidates:
            print(
                f"[ConflictDetector] No prior requirements to check against for: "
                f"{new_requirement.requirement_text[:60]!r}"
            )
            return []

        print(
            f"[ConflictDetector] Checking {len(candidates)} prior requirement(s) against: "
            f"{new_requirement.requirement_text[:60]!r}"
        )

        return self.verify_conflicts_with_llm(new_requirement, candidates)
