"""Centralized LLM client configuration."""

from openai import OpenAI
from src.core.config import Settings

_client_instance = None

def get_llm_client(settings: Settings | None = None) -> OpenAI | None:
    """
    Get a centralized OpenAI-compatible client instance.
    This routes to OpenRouter (or any other provider) based on the .env config.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    if settings is None:
        settings = Settings()

    if not settings.llm_api_key:
        return None

    _client_instance = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_api_base
    )
    return _client_instance
