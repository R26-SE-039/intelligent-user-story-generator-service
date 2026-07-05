"""Centralized LLM client configuration."""

from openai import OpenAI
import httpx
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

    # Sanitize llm_api_base: if it's accidentally set to a model name or missing protocol 
    # (e.g. from an inherited Windows environment variable), fix it.
    api_base = settings.llm_api_base
    if api_base and not (api_base.startswith("http://") or api_base.startswith("https://")):
        api_base = "https://openrouter.ai/api/v1"

    default_headers = {}
    if "openrouter.ai" in api_base:
        default_headers = {
            "HTTP-Referer": "http://localhost:5173", # Using frontend base URL
            "X-Title": "NextGenQA"
        }

    print(f"[DEBUG] llm_api_base is: '{api_base}'")

    # Bypass system proxies (HTTP_PROXY/HTTPS_PROXY) which can cause UnsupportedProtocol errors
    # if they are set in Windows without 'http://' prefixes.
    http_client = httpx.Client(trust_env=False)

    _client_instance = OpenAI(
        api_key=settings.llm_api_key,
        base_url=api_base,
        default_headers=default_headers,
        http_client=http_client
    )
    return _client_instance
