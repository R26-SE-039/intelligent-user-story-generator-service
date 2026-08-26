"""Shared pytest fixtures for the intelligent-user-story-generator-service test suite.

IMPORTANT: Several heavy dependencies hang or take minutes to import on this machine:
  - azure.cognitiveservices.speech  (C SDK, hangs without Azure keys)
  - torch                           (PyTorch, takes 5+ min to cold-start)
  - transformers                    (HuggingFace, depends on torch)

We stub ALL of them in sys.modules BEFORE any src.* import chain can trigger them.
This reduces the entire test suite startup from ~5 minutes to <5 seconds.

All fixtures are fully isolated in-memory; no live database, API, or LLM calls.
"""

from __future__ import annotations

import sys
import time
import types
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import jwt
import pytest

# ---------------------------------------------------------------------------
# Stub torch, transformers, and Azure Speech SDK BEFORE any src.* imports.
# ---------------------------------------------------------------------------

# 1. PyTorch stub (utterance_classifier.py imports torch at module level)
_torch_stub = types.ModuleType("torch")
_torch_stub.no_grad = lambda: MagicMock()
_torch_stub.cuda = types.ModuleType("torch.cuda")
_torch_stub.cuda.is_available = lambda: False
_torch_stub.Tensor = MagicMock
sys.modules["torch"] = _torch_stub
sys.modules["torch.cuda"] = _torch_stub.cuda

# 2. HuggingFace transformers stub
_transformers_stub = types.ModuleType("transformers")
_transformers_stub.AutoTokenizer = MagicMock
_transformers_stub.AutoModelForSequenceClassification = MagicMock
sys.modules["transformers"] = _transformers_stub

# 3. Azure Speech SDK stub
#    The azure package is a PEP-420 namespace package — do NOT replace
#    sys.modules['azure']; only inject the missing sub-modules.
import azure as _azure_pkg  # ensure the namespace package is loaded first

_cog_stub = types.ModuleType("azure.cognitiveservices")
_speech_stub = types.ModuleType("azure.cognitiveservices.speech")
_speech_audio_stub = types.ModuleType("azure.cognitiveservices.speech.audio")

_speech_stub.SpeechConfig = MagicMock
_speech_stub.SpeechRecognizer = MagicMock
_speech_stub.ResultReason = MagicMock()
_speech_stub.CancellationReason = MagicMock()
_speech_stub.audio = _speech_audio_stub

_speech_audio_stub.AudioStreamFormat = MagicMock
_speech_audio_stub.PushAudioInputStream = MagicMock
_speech_audio_stub.AudioConfig = MagicMock

_cog_stub.speech = _speech_stub

sys.modules["azure.cognitiveservices"] = _cog_stub
sys.modules["azure.cognitiveservices.speech"] = _speech_stub
sys.modules["azure.cognitiveservices.speech.audio"] = _speech_audio_stub
_azure_pkg.cognitiveservices = _cog_stub  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# FastAPI TestClient import (safe now that all heavy deps are stubbed)
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402



# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-key-for-pytest"
TEST_ORG_ID = "org-test-123"
TEST_USER_ID = "user-test-456"
TEST_EMAIL = "test@example.com"


# ---------------------------------------------------------------------------
# Settings / JWT helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Minimal Settings-like object for tests that need settings."""
    settings = MagicMock()
    settings.auth_secret = TEST_SECRET
    settings.environment = "test"
    settings.app_name = "Intelligent User Story Generator"
    settings.auth_service_url = "http://auth-service-mock"
    settings.cors_origins = "http://localhost:3000"
    settings.meetings_table = "meetings"
    settings.requirements_table = "requirements"
    settings.chat_messages_table = "chat_messages"
    settings.transcripts_table = "transcripts"
    settings.transcript_utterances_table = "transcript_utterances"
    settings.requirement_embeddings_table = "requirement_embeddings"
    settings.requirement_utterance_mapping_table = "requirement_utterance_mapping"
    settings.conflicts_table = "conflicts"
    settings.user_stories_table = "user_stories"
    settings.user_story_requirement_mapping_table = "user_story_requirement_mapping"
    settings.acceptance_criteria_table = "acceptance_criteria"
    settings.meeting_participants_table = "meeting_participants"
    settings.user_story_validations_table = "user_story_validations"
    return settings


@pytest.fixture
def mock_jwt_token() -> str:
    """A valid signed JWT token containing user/org context."""
    payload = {
        "userId": TEST_USER_ID,
        "sub": TEST_USER_ID,
        "email": TEST_EMAIL,
        "role": "BA",
        "organizationId": TEST_ORG_ID,
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture
def mock_auth_headers(mock_jwt_token: str) -> dict[str, str]:
    """HTTP Authorization headers with the test JWT."""
    return {"Authorization": f"Bearer {mock_jwt_token}"}


# ---------------------------------------------------------------------------
# Database gateway mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_gateway(mock_settings) -> MagicMock:
    """A fully mocked PostgresGateway instance.

    All database operations are no-ops unless overridden in a specific test.
    """
    gateway = MagicMock()
    gateway.settings = mock_settings
    gateway.select.return_value = []
    gateway.insert.return_value = None
    gateway.update.return_value = None
    gateway.upsert.return_value = None
    gateway.execute_query.return_value = []
    return gateway


# ---------------------------------------------------------------------------
# FastAPI TestClient — minimal isolated app (no src.main module-level code)
# ---------------------------------------------------------------------------


def _build_base_mock_settings():
    """Build a stand-alone mock Settings without relying on a fixture scope."""
    s = MagicMock()
    s.auth_secret = TEST_SECRET
    s.environment = "test"
    s.app_name = "Intelligent User Story Generator"
    s.auth_service_url = "http://auth-service-mock"
    s.cors_origins = "http://localhost:3000"
    s.meetings_table = "meetings"
    s.requirements_table = "requirements"
    s.chat_messages_table = "chat_messages"
    s.transcripts_table = "transcripts"
    s.transcript_utterances_table = "transcript_utterances"
    s.requirement_embeddings_table = "requirement_embeddings"
    s.requirement_utterance_mapping_table = "requirement_utterance_mapping"
    s.conflicts_table = "conflicts"
    s.user_stories_table = "user_stories"
    s.user_story_requirement_mapping_table = "user_story_requirement_mapping"
    s.acceptance_criteria_table = "acceptance_criteria"
    s.meeting_participants_table = "meeting_participants"
    s.user_story_validations_table = "user_story_validations"
    return s


def _make_test_app():
    """Create a minimal FastAPI app that contains only the routes under test.

    Avoids importing src.main (which has module-level Settings() and DB connect).
    Azure SDK is already stubbed via sys.modules at module load time.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    mock_s = _build_base_mock_settings()

    @asynccontextmanager
    async def _noop_lifespan(app):
        app.state.settings = mock_s
        app.state.gateway = MagicMock()
        app.state.speech_settings = MagicMock()
        app.state.azure_speech = MagicMock()
        app.state.meeting_repo = MagicMock()
        app.state.req_repo = MagicMock()
        app.state.transcript_repo = MagicMock()
        app.state.conflict_repo = MagicMock()
        app.state.transcription_service = MagicMock()
        app.state.ws_manager = MagicMock()
        app.state.req_extractor = MagicMock()
        app.state.conflict_detector = MagicMock()
        app.state.thread_service = MagicMock()
        app.state.live_meeting_service = MagicMock()
        app.state.meeting_coordinator = MagicMock()
        app.state.story_pipeline = MagicMock()
        app.state.story_repo = MagicMock()
        yield

    app = FastAPI(title="Test App", lifespan=_noop_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routes.user_stories import router as user_stories_router
    from src.api.routes.jira import router as jira_router

    app.include_router(user_stories_router, prefix="/api/v1/pipeline")
    app.include_router(jira_router, prefix="/api/v1/jira")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "intelligent-user-story-generator",
            "environment": mock_s.environment,
        }

    return app, mock_s


@pytest.fixture
def client(mock_settings) -> TestClient:  # type: ignore[type-arg]
    """FastAPI TestClient wrapping a minimal isolated test app.

    No real Postgres, Azure Speech, or LLM connections are made.
    """
    app, app_settings = _make_test_app()

    from src.api.dependencies import get_current_user, get_settings

    def _override_user() -> dict[str, Any]:
        return {
            "id": TEST_USER_ID,
            "email": TEST_EMAIL,
            "role": "BA",
            "organization_id": TEST_ORG_ID,
        }

    def _override_settings() -> Any:
        return app_settings

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_settings] = _override_settings

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
