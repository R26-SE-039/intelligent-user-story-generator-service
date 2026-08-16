"""Layer 4 — INVEST Validation via Gemini LLM.

Evaluates the generated user story against the six INVEST principles
(Independent, Negotiable, Valuable, Estimable, Small, Testable) using
the Gemini LLM with a structured JSON prompt.

Expected LLM JSON response shape:
    {
      "Independent": 0.9,
      "Negotiable": 0.8,
      "Valuable": 1.0,
      "Estimable": 0.7,
      "Small": 0.85,
      "Testable": 0.95,
      "overall_invest_score": 0.87,
      "feedback": { ... },
      "improvement_suggestions": [...]
    }
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from google import genai

from src.models.user_story import InvestScore

LOGGER = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "invest_validation_prompt.txt"


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
        LOGGER.warning("[InvestValidator] Could not parse LLM JSON response.")
        return {}


class InvestValidator:
    """Score a user story against INVEST principles using Gemini LLM."""

    def __init__(self, genai_client: genai.Client, model: str) -> None:
        self._client = genai_client
        self._model = model
        self._system_prompt = _load_prompt()

    def validate(
        self,
        story_text: str,
        acceptance_criteria: list[str],
    ) -> tuple[InvestScore, float, list[str]]:
        """Evaluate the story against INVEST principles.

        Args:
            story_text: The full user story string.
            acceptance_criteria: List of AC strings for this story.

        Returns:
            A tuple of:
            - ``invest_score`` — an :class:`InvestScore` with per-principle floats (0–1)
            - ``overall_invest_score_5`` — overall score normalised to 0–5 scale
            - ``improvement_suggestions`` — list of improvement suggestion strings
        """
        ac_text = "\n".join(f"- {ac}" for ac in acceptance_criteria) if acceptance_criteria else "None provided."

        input_payload = (
            f"{self._system_prompt}\n\n"
            f"=== USER STORY ===\n{story_text}\n\n"
            f"=== ACCEPTANCE CRITERIA ===\n{ac_text}"
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=input_payload,
            )
            raw = response.text or "{}"
            data = _extract_json(raw)

            # Parse per-principle scores
            invest = InvestScore(
                Independent=float(data.get("Independent", 1.0)),
                Negotiable=float(data.get("Negotiable", 1.0)),
                Valuable=float(data.get("Valuable", 1.0)),
                Estimable=float(data.get("Estimable", 1.0)),
                Small=float(data.get("Small", 1.0)),
                Testable=float(data.get("Testable", 1.0)),
            )

            # Clamp all values to [0, 1]
            invest = InvestScore(
                Independent=max(0.0, min(1.0, invest.Independent)),
                Negotiable=max(0.0, min(1.0, invest.Negotiable)),
                Valuable=max(0.0, min(1.0, invest.Valuable)),
                Estimable=max(0.0, min(1.0, invest.Estimable)),
                Small=max(0.0, min(1.0, invest.Small)),
                Testable=max(0.0, min(1.0, invest.Testable)),
            )

            # Overall on a 0-5 scale (sum of 6 principles, each 0-1, /6*5)
            overall_5 = round(invest.overall * 5.0, 2)
            suggestions: list[str] = data.get("improvement_suggestions", [])

            LOGGER.debug(
                "[InvestValidator] overall=%.2f/5 → %s",
                overall_5,
                invest.model_dump(),
            )
            return invest, overall_5, suggestions

        except Exception as exc:
            LOGGER.warning("[InvestValidator] LLM call failed: %s — using defaults.", exc)
            default = InvestScore()
            return default, 5.0, []
