"""Layer 3 — Hallucination Detection via Gemini LLM.

Asks the Gemini LLM to determine whether every statement in a generated
user story is grounded in the retrieved transcript evidence.

Expected LLM JSON response shape:
    {
      "supported": true,
      "unsupported_claims": [],
      "hallucination_score": 0.02,
      "confidence": 0.98,
      "reasoning": "..."
    }
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from google import genai

from src.models.transcript import Chunk

LOGGER = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "hallucination_detection_prompt.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        LOGGER.warning("[HallucinationDetector] Could not parse LLM JSON response.")
        return {}


class HallucinationDetector:
    """Detect unsupported claims in generated user stories using Gemini LLM."""

    def __init__(self, genai_client: genai.Client, model: str) -> None:
        self._client = genai_client
        self._model = model
        self._system_prompt = _load_prompt()

    def detect(
        self,
        story_text: str,
        evidence_chunks: list[Chunk],
    ) -> tuple[float, float, list[str]]:
        """Evaluate hallucination risk for a single story.

        Args:
            story_text: The full user story string.
            evidence_chunks: Retrieved transcript evidence chunks.

        Returns:
            A tuple of:
            - ``hallucination_score`` — float 0.0 (clean) to 1.0 (hallucinated)
            - ``confidence`` — LLM confidence in its own assessment (0.0–1.0)
            - ``unsupported_claims`` — list of identified unsupported claim strings
        """
        if not evidence_chunks:
            LOGGER.warning("[HallucinationDetector] No evidence chunks — skipping LLM call.")
            return 0.5, 0.5, ["No evidence available to validate against."]

        evidence_text = "\n---\n".join(
            f"[Chunk {i + 1}] {chunk.text}" for i, chunk in enumerate(evidence_chunks)
        )

        input_payload = (
            f"{self._system_prompt}\n\n"
            f"=== USER STORY ===\n{story_text}\n\n"
            f"=== EVIDENCE FROM MEETING TRANSCRIPT ===\n{evidence_text}"
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=input_payload,
            )
            raw = response.text or "{}"
            data = _extract_json(raw)

            hallucination_score = float(data.get("hallucination_score", 0.5))
            confidence = float(data.get("confidence", 0.5))
            unsupported_claims: list[str] = data.get("unsupported_claims", [])

            # Clamp scores to valid ranges
            hallucination_score = max(0.0, min(1.0, hallucination_score))
            confidence = max(0.0, min(1.0, confidence))

            return hallucination_score, confidence, unsupported_claims

        except Exception as exc:
            LOGGER.warning("[HallucinationDetector] LLM call failed: %s — using defaults.", exc)
            return 0.5, 0.5, []
