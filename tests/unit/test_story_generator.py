"""Unit tests for StoryGenerator with mocked LLM client.

All LLM API calls are intercepted; no real API keys are needed.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.models.transcript import Chunk
from src.models.user_story import GeneratedStory, StoryBatch


def _make_chunk(chunk_id: str = "chunk-001", text: str = "We need a login feature.") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        transcript_id="transcript-001",
        chunk_index=0,
        text=text,
        speakers=["Alice"],
        timestamp_start=0.0,
        timestamp_end=5.0,
    )


def _make_story_payload(story_id: str | None = None) -> dict:
    return {
        "story_id": story_id or str(uuid.uuid4()),
        "title": "User Login",
        "story": "As a user, I want to log in, so that I can access my dashboard.",
        "acceptance_criteria": [
            "Given I am on the login page When I enter valid credentials Then I am redirected."
        ],
        "priority": "Must",
        "confidence": 0.9,
        "status": "ready",
        "clarification_questions": [],
        "evidence_refs": ["chunk-001"],
    }


@pytest.fixture
def story_generator():
    """StoryGenerator instance with a mocked LLM client."""
    with patch("src.services.generation.story_generator.get_llm_client") as mock_llm_factory:
        mock_client = MagicMock()
        mock_llm_factory.return_value = mock_client

        from src.services.generation.story_generator import StoryGenerator

        generator = StoryGenerator(api_key="test-key")
        generator.client = mock_client
        yield generator, mock_client


class TestStoryGeneratorFallback:
    """When client is None, fallback story is generated."""

    def test_fallback_with_evidence_returns_one_story(self):
        with patch("src.services.generation.story_generator.get_llm_client", return_value=None):
            from src.services.generation.story_generator import StoryGenerator

            gen = StoryGenerator.__new__(StoryGenerator)
            gen.client = None

            chunk = _make_chunk()
            batch = gen._generate_fallback("Login feature", [chunk])
            assert isinstance(batch, StoryBatch)
            assert len(batch.stories) == 1

    def test_fallback_with_no_evidence_returns_empty_batch(self):
        with patch("src.services.generation.story_generator.get_llm_client", return_value=None):
            from src.services.generation.story_generator import StoryGenerator

            gen = StoryGenerator.__new__(StoryGenerator)
            gen.client = None
            batch = gen._generate_fallback("Login", [])
            assert batch.stories == []

    def test_generate_uses_fallback_when_client_none(self):
        with patch("src.services.generation.story_generator.get_llm_client", return_value=None):
            from src.services.generation.story_generator import StoryGenerator

            gen = StoryGenerator.__new__(StoryGenerator)
            gen.client = None

            chunk = _make_chunk()
            batch = gen.generate("Test query", [chunk])
            assert isinstance(batch, StoryBatch)


class TestStoryGeneratorJsonParsing:
    """_generate_with_genai correctly parses different LLM output formats."""

    def test_parses_plain_json_response(self, story_generator):
        generator, mock_client = story_generator
        payload = {"stories": [_make_story_payload()]}

        mock_interaction = MagicMock()
        mock_interaction.output_text = json.dumps(payload)
        mock_client.interactions.create.return_value = mock_interaction

        # Temporarily stub _load_prompt to avoid file I/O
        generator._load_prompt = MagicMock(return_value="prompt text")

        batch = generator._generate_with_genai("Login", [_make_chunk()])
        assert isinstance(batch, StoryBatch)
        assert len(batch.stories) == 1
        assert batch.stories[0].title == "User Login"

    def test_parses_markdown_fenced_json_response(self, story_generator):
        generator, mock_client = story_generator
        payload = {"stories": [_make_story_payload()]}
        markdown_response = f"```json\n{json.dumps(payload)}\n```"

        mock_interaction = MagicMock()
        mock_interaction.output_text = markdown_response
        mock_client.interactions.create.return_value = mock_interaction

        generator._load_prompt = MagicMock(return_value="prompt text")

        batch = generator._generate_with_genai("Login", [_make_chunk()])
        assert isinstance(batch, StoryBatch)
        assert len(batch.stories) == 1

    def test_parses_list_response_wrapped_into_batch(self, story_generator):
        generator, mock_client = story_generator
        # Model returns a raw list instead of {\"stories\": [...]}
        payload = [_make_story_payload()]

        mock_interaction = MagicMock()
        mock_interaction.output_text = json.dumps(payload)
        mock_client.interactions.create.return_value = mock_interaction

        generator._load_prompt = MagicMock(return_value="prompt text")

        batch = generator._generate_with_genai("Login", [_make_chunk()])
        assert isinstance(batch, StoryBatch)
        assert len(batch.stories) == 1

    def test_raises_on_completely_invalid_json(self, story_generator):
        generator, mock_client = story_generator

        mock_interaction = MagicMock()
        mock_interaction.output_text = "THIS IS NOT JSON AT ALL"
        mock_client.interactions.create.return_value = mock_interaction

        generator._load_prompt = MagicMock(return_value="prompt text")

        with pytest.raises(Exception):
            generator._generate_with_genai("Login", [_make_chunk()])
