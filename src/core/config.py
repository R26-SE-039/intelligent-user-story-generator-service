"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the unified intelligent user story generator service."""

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

    # PostgreSQL Database
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="postgres", alias="DB_PASSWORD")
    db_name: str = Field(default="agile_meeting_db", alias="DB_NAME")
    
    meetings_table: str = Field(default="meetings", alias="DB_MEETINGS_TABLE")
    chat_messages_table: str = Field(default="chat_messages", alias="DB_CHAT_MESSAGES_TABLE")
    transcripts_table: str = Field(default="transcripts", alias="DB_TRANSCRIPTS_TABLE")
    transcript_utterances_table: str = Field(default="transcript_utterances", alias="DB_TRANSCRIPT_UTTERANCES_TABLE")
    requirements_table: str = Field(default="requirements", alias="DB_REQUIREMENTS_TABLE")
    requirement_embeddings_table: str = Field(default="requirement_embeddings", alias="DB_REQUIREMENT_EMBEDDINGS_TABLE")
    requirement_utterance_mapping_table: str = Field(default="requirement_utterance_mapping", alias="DB_REQUIREMENT_UTTERANCE_MAPPING_TABLE")
    conflicts_table: str = Field(default="conflicts", alias="DB_CONFLICTS_TABLE")
    user_stories_table: str = Field(default="user_stories", alias="DB_USER_STORIES_TABLE")
    user_story_requirement_mapping_table: str = Field(default="user_story_requirement_mapping", alias="DB_USER_STORY_REQUIREMENT_MAPPING_TABLE")
    acceptance_criteria_table: str = Field(default="acceptance_criteria", alias="DB_ACCEPTANCE_CRITERIA_TABLE")

    # Azure Speech Service
    azure_speech_key: str = Field(default="", alias="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(default="southeastasia", alias="AZURE_SPEECH_REGION")

    # Auth
    auth_secret: str = Field(default="dev-change-me-secret", alias="AUTH_SECRET")

    # Speech transcription tuning
    transcription_timeout_seconds: int = Field(default=120, alias="TRANSCRIPTION_TIMEOUT_SECONDS")
    transcription_poll_interval_seconds: float = Field(default=1.2, alias="TRANSCRIPTION_POLL_INTERVAL_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )
