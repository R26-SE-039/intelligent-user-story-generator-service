"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for API, models, and retrieval pipeline."""

    app_env: str = "dev"

    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_api_base: str = Field(default="https://openrouter.ai/api/v1", alias="LLM_API_BASE")
    chat_model: str = Field(default="meta-llama/llama-3.1-70b-instruct", alias="CHAT_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")

    chroma_persist_directory: Path = Field(default=Path("data/vector_index/chroma"), alias="CHROMA_PERSIST_DIRECTORY")
    vector_db_collection: str = Field(default="transcript_chunks", alias="VECTOR_DB_COLLECTION")

    chunk_size_words: int = Field(default=220, alias="CHUNK_SIZE_WORDS")
    chunk_overlap_words: int = Field(default=40, alias="CHUNK_OVERLAP_WORDS")
    retrieval_top_k: int = Field(default=8, alias="RETRIEVAL_TOP_K")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )
