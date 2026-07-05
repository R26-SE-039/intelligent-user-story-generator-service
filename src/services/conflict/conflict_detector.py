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
MAX_CANDIDATES = 20


class ConflictDetectorService:
    """
    Detects conflicts between a newly extracted requirement and ALL existing ones
    in the same meeting using direct LLM-based logical contradiction checking.

    NOTE: The previous two-stage pipeline (pgvector similarity → LLM) was replaced
    because the system uses hash-based fallback embeddings (not semantic embeddings)
    when OpenRouter is the LLM provider. Hash embeddings have no semantic meaning,
    so cosine distance between related requirements was always > threshold, meaning
    zero candidates ever reached the LLM.

    The new pipeline:
      1. Fetch ALL requirements from this meeting (excluding the new one) from DB.
      2. Pass them directly to the LLM for logical contradiction verification.
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
        the new requirement. Returns confirmed Conflict objects only.
        """
        if not candidates or not self.client:
            return []

        system_prompt = self._load_prompt("conflict_detection_prompt.txt")

        # Format the user message: new requirement + numbered list of all existing ones
        candidate_lines = "\n".join(
            f"{i + 1}. [{c['requirement_type']}] {c['requirement_text']}"
            for i, c in enumerate(candidates)
        )
        user_message = (
            f"NEW REQUIREMENT:\n[{new_req.requirement_type}] {new_req.requirement_text}\n\n"
            f"EXISTING REQUIREMENTS TO CHECK:\n{candidate_lines}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,   # Deterministic for classification tasks
                max_tokens=1500,   # Prevent 402 from OpenRouter credit limit assumption
            )

            content = response.choices[0].message.content.strip()
            print(f"[ConflictDetector] LLM raw response: {content[:300]}")

            # Strip any accidental markdown fences
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
                    conflicts.append(
                        Conflict(
                            conflict_id=str(uuid4()),
                            requirement_a_id=new_req.requirement_id,
                            requirement_b_id=candidate["id"],
                            conflict_type=result.get("conflict_type", "functional"),
                            severity=result.get("severity", "medium"),
                            explanation=result.get("explanation", ""),
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
        req_repository,  # RequirementRepository (injected to avoid circular import)
    ) -> list[Conflict]:
        """
        Full conflict detection pipeline for one new requirement.

        Fetches ALL existing requirements for the meeting from the DB and sends
        them directly to the LLM for conflict analysis. The embedding-based
        pre-filter is intentionally omitted because hash fallback embeddings have
        no semantic meaning and would incorrectly eliminate all candidates.
        """
        try:
            all_existing = req_repository.get_all_for_conflict_check(
                meeting_id=new_requirement.meeting_id,
                exclude_id=new_requirement.requirement_id,
            )
        except Exception as e:
            print(f"[ConflictDetector] DB fetch error: {e}")
            return []

        if not all_existing:
            print(
                f"[ConflictDetector] No prior requirements to check against for: "
                f"{new_requirement.requirement_text[:60]!r}"
            )
            return []

        # Cap at MAX_CANDIDATES to avoid exceeding LLM context window
        candidates = all_existing[:MAX_CANDIDATES]

        print(
            f"[ConflictDetector] Checking {len(candidates)} prior requirement(s) against: "
            f"{new_requirement.requirement_text[:60]!r}"
        )

        return self.verify_conflicts_with_llm(new_requirement, candidates)
