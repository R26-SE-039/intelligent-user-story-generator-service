"""Integration tests for the pipeline API endpoints.

Routes under test:
  POST /api/v1/pipeline/run
  POST /api/v1/pipeline/generate-from-requirements
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.api.dependencies import get_current_user
from src.models.schemas import (
    PipelineRunResponse,
    PipelineRunRequest,
    GeneratedStory,
    StoryBatch,
    ValidationResult,
)
from src.models.transcript import Transcript, Utterance


def _make_pipeline_response(transcript_id: str | None = None) -> dict:
    """Build a serializable PipelineRunResponse payload."""
    story_id = str(uuid.uuid4())
    return {
        "transcript_id": transcript_id or str(uuid.uuid4()),
        "meeting_id": None,
        "indexed_chunks": 3,
        "query": "Generate user stories",
        "stories": [
            {
                "story_id": story_id,
                "title": "User Login",
                "story": "As a user, I want to log in, so that I can access my dashboard.",
                "acceptance_criteria": [
                    "Given I enter credentials When I submit Then I am authenticated."
                ],
                "priority": "Must",
                "confidence": 0.9,
                "status": "ready",
                "clarification_questions": [],
                "evidence_refs": ["chunk-001"],
            }
        ],
        "issues": [],
        "evidence_chunk_ids": ["chunk-001"],
        "validation_results": [],
    }


def _make_transcript_payload() -> dict:
    """Build a minimal Transcript payload as a dict."""
    return {
        "transcript_id": str(uuid.uuid4()),
        "utterances": [
            {
                "speaker": "Alice",
                "text": "We need a login feature for the users.",
                "timestamp_start": 0.0,
                "timestamp_end": 5.0,
            }
        ],
    }


class TestPipelineRunEndpoint:
    """POST /api/v1/pipeline/run"""

    def test_successful_pipeline_run_returns_200(self, client):
        expected_response = _make_pipeline_response()

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = PipelineRunResponse(**expected_response)

        from src.api.dependencies import get_story_pipeline

        client.app.dependency_overrides[get_story_pipeline] = lambda: mock_pipeline

        try:
            response = client.post(
                "/api/v1/pipeline/run",
                json={
                    "transcript": _make_transcript_payload(),
                    "query": "Generate user stories",
                },
            )
        finally:
            client.app.dependency_overrides.pop(get_story_pipeline, None)

        # Pipeline run returns 200 when successful
        assert response.status_code == 200

    def test_pipeline_run_returns_stories_in_response(self, client):
        expected_response = _make_pipeline_response()

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = PipelineRunResponse(**expected_response)

        from src.api.dependencies import get_story_pipeline

        client.app.dependency_overrides[get_story_pipeline] = lambda: mock_pipeline

        try:
            response = client.post(
                "/api/v1/pipeline/run",
                json={
                    "transcript": _make_transcript_payload(),
                    "query": "Generate user stories",
                },
            )
        finally:
            client.app.dependency_overrides.pop(get_story_pipeline, None)

        data = response.json()
        assert "stories" in data

    def test_pipeline_run_returns_400_on_value_error(self, client):
        mock_pipeline = MagicMock()
        mock_pipeline.run.side_effect = ValueError("Invalid transcript format")

        from src.api.dependencies import get_story_pipeline

        client.app.dependency_overrides[get_story_pipeline] = lambda: mock_pipeline

        try:
            response = client.post(
                "/api/v1/pipeline/run",
                json={
                    "transcript": _make_transcript_payload(),
                    "query": "Generate user stories",
                },
            )
        finally:
            client.app.dependency_overrides.pop(get_story_pipeline, None)

        assert response.status_code == 400
        assert "Pipeline Validation Error" in response.json()["detail"]

    def test_pipeline_run_returns_422_for_missing_required_fields(self, client):
        # Missing the required 'transcript' field
        response = client.post(
            "/api/v1/pipeline/run",
            json={"query": "Generate user stories"},
        )
        assert response.status_code == 422


class TestGenerateFromRequirementsEndpoint:
    """POST /api/v1/pipeline/generate-from-requirements"""

    def test_missing_auth_returns_401(self, client):
        """Without a valid Authorization header, the upload endpoint rejects the request with 401."""
        client.app.dependency_overrides.pop(get_current_user, None)

        response = client.post(
            "/api/v1/pipeline/upload",
            data={"query": "Generate user stories"},
            files={"file": ("test.txt", b"Sample transcript text", "text/plain")},
        )

        # Restore auth override for subsequent tests
        client.app.dependency_overrides[get_current_user] = lambda: {
            "id": "user-test-456",
            "email": "test@example.com",
            "role": "BA",
            "organization_id": "org-test-123",
        }

        assert response.status_code == 401


    def test_successful_generation_returns_200(self, client, mock_auth_headers):
        meeting_id = str(uuid.uuid4())

        mock_us_service = MagicMock()
        mock_us_service.generate_from_requirements.return_value = {
            "meeting_id": meeting_id,
            "stories": [],
            "validation_results": [],
        }

        from src.api.dependencies import get_user_story_service

        client.app.dependency_overrides[get_user_story_service] = lambda: mock_us_service

        try:
            response = client.post(
                "/api/v1/pipeline/generate-from-requirements",
                json={"meeting_id": meeting_id},
                headers=mock_auth_headers,
            )
        finally:
            client.app.dependency_overrides.pop(get_user_story_service, None)

        assert response.status_code == 200

