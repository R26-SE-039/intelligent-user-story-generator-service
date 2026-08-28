import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_SECRET"] = "next_gen_qa_auth_super_secret_jwt_for_production_test_key_32bytes"
os.environ["DATABASE_URL"] = "postgresql://mock:mock@localhost:5432/test"
os.environ["AZURE_SPEECH_KEY"] = "mock-key"
os.environ["AZURE_SPEECH_REGION"] = "southeastasia"
os.environ["LLM_API_KEY"] = "mock-llm-key"
os.environ["MODERNBERT_MODEL_PATH"] = "models/modernbert-utterance-classifier"

from src.main import app
from src.core.config import Settings


@pytest.fixture(scope="session")
def client():
    """Create a FastAPI TestClient instance for testing."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    """Helper fixture to generate test authorization headers."""
    import jwt
    import time
    secret = os.environ.get("AUTH_SECRET", "next_gen_qa_auth_super_secret_jwt_for_production_test_key_32bytes")
    payload = {
        "userId": "test-user-id-123",
        "email": "test@example.com",
        "role": "ORGANIZATION_OWNER",
        "exp": int(time.time()) + 3600
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}