"""Real-time conflict detection service for requirements."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from src.core.llm import get_llm_client
from src.core.config import Settings
from src.models.conflict import Conflict
from src.models.requirement import Requirement


# Cosine distance threshold — candidates with distance > this value are too dissimilar
# to bother sending to the LLM. 0.0 = identical, 1.0 = completely different.
# A value of 0.5 means we only check semantically related requirements.
SIMILARITY_THRESHOLD = 0.55


class ConflictDetectorService:
    """
    Detects conflicts between a newly extracted requirement and existing ones
    in the same meeting using a two-stage pipeline:
      1. pgvector cosine similarity filter (fast, cheap)
      2. LLM-based logical contradiction check (accurate)
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
        Ask the LLM to verify which candidates actually conflict with the new requirement.
        Returns a list of Conflict objects for confirmed conflicts only.
        """
        if not candidates or not self.client:
            return []

        system_prompt = self._load_prompt("conflict_detection_prompt.txt")

        # Format the user message: new requirement + numbered list of candidates
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
                temperature=0.0,  # Deterministic for classification tasks
            )

            content = response.choices[0].message.content.strip()

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
            return []

    def detect(
        self,
        new_requirement: Requirement,
        embedding: list[float],
        req_repository,  # RequirementRepository (injected to avoid circular import)
        top_k: int = 5,
    ) -> list[Conflict]:
        """
        Full conflict detection pipeline for one new requirement.
        
        1. Use pgvector similarity to find top-K most similar existing requirements.
        2. Filter by SIMILARITY_THRESHOLD to cut out unrelated requirements.
        3. Pass the shortlist to the LLM for logical contradiction verification.
        4. Return confirmed Conflict objects.
        """
        # Stage 1: Similarity filter
        try:
            similar = req_repository.find_similar_by_embedding(
                embedding=embedding,
                meeting_id=new_requirement.meeting_id,
                top_k=top_k,
                exclude_id=new_requirement.requirement_id,
            )
        except Exception as e:
            print(f"[ConflictDetector] Similarity search error: {e}")
            return []

        # Apply threshold — only keep semantically close candidates
        candidates = [r for r in similar if r.get("distance", 1.0) <= SIMILARITY_THRESHOLD]

        if not candidates:
            print(
                f"[ConflictDetector] No close candidates found for: "
                f"{new_requirement.requirement_text[:60]!r}"
            )
            return []

        print(
            f"[ConflictDetector] Checking {len(candidates)} candidate(s) against: "
            f"{new_requirement.requirement_text[:60]!r}"
        )

        # Stage 2: LLM verification
        return self.verify_conflicts_with_llm(new_requirement, candidates)
