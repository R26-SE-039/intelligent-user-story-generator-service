"""Centralized LLM client configuration."""

from google import genai
import httpx
from src.core.config import Settings

_client_instance = None

def get_llm_client(settings: Settings | None = None) -> genai.Client | None:
    """
    Get a centralized Google GenAI client instance.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    if settings is None:
        settings = Settings()

    if not settings.llm_api_key:
        return None

    _client_instance = genai.Client(api_key=settings.llm_api_key)
    return _client_instance
