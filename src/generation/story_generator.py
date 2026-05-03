"""Generate user stories and acceptance criteria from retrieved context."""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from src.models.schemas import Chunk, GeneratedStory, StoryBatch


class StoryGenerator:
	"""Generate user stories using an LLM with deterministic fallback for local runs."""

	def __init__(self, api_key: str | None, model_name: str, api_base: str = "https://openrouter.io/api/v1") -> None:
		self.api_key = api_key
		self.model_name = model_name
		self.api_base = api_base
		self.client = OpenAI(api_key=api_key, base_url=api_base) if api_key else None
		self.prompts_dir = Path(__file__).resolve().parent / "prompts"

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

	def _generate_with_openai(self, query: str, evidence: list[Chunk]) -> StoryBatch:
		system_prompt = self._load_prompt("system_guardrail_prompt.txt")
		story_prompt = self._load_prompt("story_generation_prompt.txt")
		completion = self.client.chat.completions.create(
			model=self.model_name,
			temperature=0.2,
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": story_prompt},
				{"role": "user", "content": self._build_input_payload(query, evidence)},
			],
		)
		content = completion.choices[0].message.content or "{}"
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
		return self._generate_with_openai(query, evidence)
