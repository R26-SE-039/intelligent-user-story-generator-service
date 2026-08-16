"""Generate user stories and acceptance criteria from retrieved context."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.config import Settings
from src.core.llm import get_llm_client
from src.models.transcript import Chunk
from src.models.user_story import GeneratedStory, StoryBatch


class StoryGenerator:
    """Generate user stories using an LLM with deterministic fallback for local runs."""

    def __init__(self, api_key: str | None = None, api_base: str | None = None, model: str = "gemini-2.0-flash") -> None:
        """Initialize StoryGenerator with a Gemini GenAI client."""
        settings = Settings()
        if api_key:
            settings.llm_api_key = api_key
        # api_base is accepted but ignored — the system uses google.genai exclusively
        
        self.client = get_llm_client(settings)
        self.model = model
        # Prompts are in src/prompts/
        self.prompts_dir = Path(__file__).resolve().parent.parent.parent / "prompts"

    def _load_prompt(self, name: str) -> str:
        return (self.prompts_dir / name).read_text(encoding="utf-8")

    def _build_input_payload(self, query: str, evidence: list[Chunk]) -> str:
        payload = {
            "query": query,
            "evidence": [
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "speakers": c.speakers,
                    "timestamp_start": c.timestamp_start,
                    "timestamp_end": c.timestamp_end,
                }
                for c in evidence
            ],
        }
        return json.dumps(payload, ensure_ascii=True)

    def _generate_with_genai(self, query: str, evidence: list[Chunk]) -> StoryBatch:
        system_prompt = self._load_prompt("system_guardrail_prompt.txt")
        story_prompt = self._load_prompt("story_generation_prompt.txt")
        input_text = f"System Instructions:\n{system_prompt}\n\nTask:\n{story_prompt}\n\nInput Data:\n{self._build_input_payload(query, evidence)}"
        
        interaction = self.client.interactions.create(
            model=self.model,
            input=input_text,
            response_format={
                "type": "text",
                "mime_type": "application/json"
            }
        )
        content = interaction.output_text or "{}"
        # Extract JSON block if model wraps it in markdown code fences
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            content = match.group(1).strip() if match else content
        data = json.loads(content)
        # Resilience: If the model returns a list instead of {"stories": []}
        if isinstance(data, list):
            data = {"stories": data}
        return StoryBatch.model_validate(data)

    def _generate_fallback(self, query: str, evidence: list[Chunk]) -> StoryBatch:
        if not evidence:
            return StoryBatch(stories=[])

        references = [chunk.chunk_id for chunk in evidence[:3]]
        summary_line = evidence[0].text.splitlines()[0][:120]
        story = GeneratedStory(
            story_id="US-001",
            title="Capture request from transcript",
            story=f"As a product manager, I want to address '{query}', so that stakeholders receive the expected outcome.",
            acceptance_criteria=[
                "Given the transcript evidence is available When stories are generated Then each story references source chunks.",
                "Given a stakeholder request appears in a transcript When the pipeline runs Then a user story is produced in standard format.",
                f"Given evidence '{summary_line}' When reviewing output Then the story remains grounded in transcript facts.",
            ],
            priority="Should",
            confidence=0.65,
            status="ready",
            clarification_questions=[],
            evidence_refs=references,
        )
        return StoryBatch(stories=[story])

    def generate(self, query: str, evidence: list[Chunk]) -> StoryBatch:
        """Generate stories from evidence chunks using configured LLM or fallback."""
        if self.client is None:
            return self._generate_fallback(query, evidence)
        return self._generate_with_genai(query, evidence)

    def generate_from_requirements(self, requirements: list[dict]) -> StoryBatch:
        """Generate stories directly from finalized requirements list."""
        if self.client is None or not requirements:
            return StoryBatch(stories=[])
            
        system_prompt = self._load_prompt("system_guardrail_prompt.txt")
        story_prompt = self._load_prompt("story_from_requirements_prompt.txt")
        
        # Build requirements payload
        payload = {
            "requirements": [
                {
                    "id": req["id"],
                    "text": req["requirement_text"],
                    "type": req["requirement_type"]
                }
                for req in requirements
            ]
        }
        
        input_text = f"System Instructions:\n{system_prompt}\n\nTask:\n{story_prompt}\n\nInput Data:\n{json.dumps(payload, ensure_ascii=True)}"
        interaction = self.client.interactions.create(
            model=self.model,
            input=input_text,
            response_format={
                "type": "text",
                "mime_type": "application/json"
            }
        )
        content = interaction.output_text or "{}"
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            content = match.group(1).strip() if match else content
        data = json.loads(content)
        if isinstance(data, list):
            data = {"stories": data}
        return StoryBatch.model_validate(data)

