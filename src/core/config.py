"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class PostgresSettings:
    """Environment-driven PostgreSQL configuration."""

    host: str
    port: int
    user: str
    password: str
    dbname: str
    meetings_table: str
    chat_messages_table: str
    transcripts_table: str
    transcript_utterances_table: str
    requirements_table: str
    requirement_embeddings_table: str
    requirement_utterance_mapping_table: str
    conflicts_table: str
    user_stories_table: str
    user_story_requirement_mapping_table: str
    acceptance_criteria_table: str
    meeting_participants_table: str
    user_story_validations_table: str
    sslmode: str = "disable"

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.user and self.dbname)


@dataclass(frozen=True)
class SpeechServiceSettings:
    """Runtime settings for speech/meeting features."""

    transcription_timeout_seconds: int
    polling_interval_seconds: float
    cors_origins: list[str]
    auth_secret: str
    azure_speech_key: str
    azure_speech_region: str
    frontend_base_url: str


class Settings(BaseSettings):
    """Runtime settings for the unified intelligent user story generator service."""

    environment: str = Field(default="development", alias="ENVIRONMENT")
    app_name: str = Field(default="Intelligent User Story Generator", alias="APP_NAME")
    port: int = Field(default=8001, alias="PORT")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173", alias="CORS_ORIGINS")

    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    chat_model: str = Field(default="gemini-2.0-flash", alias="CHAT_MODEL")
    embedding_model: str = Field(default="models/gemini-embedding-001", alias="EMBEDDING_MODEL")

    chroma_persist_directory: Path = Field(default=Path("data/vector_index/chroma"), alias="CHROMA_PERSIST_DIRECTORY")
    vector_db_collection: str = Field(default="transcript_chunks", alias="VECTOR_DB_COLLECTION")
    modernbert_model_path: Path = Field(default=Path("models/modernbert-utterance-classifier"), alias="MODERNBERT_MODEL_PATH")

    chunk_size_words: int = Field(default=220, alias="CHUNK_SIZE_WORDS")
    chunk_overlap_words: int = Field(default=40, alias="CHUNK_OVERLAP_WORDS")
    retrieval_top_k: int = Field(default=8, alias="RETRIEVAL_TOP_K")

    # PostgreSQL Database
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="postgres", alias="DB_PASSWORD")
    db_name: str = Field(default="agile_meeting_db", alias="DB_NAME")
    db_sslmode: str = Field(default="disable", alias="DB_SSLMODE")
    
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
    meeting_participants_table: str = Field(default="meeting_participants", alias="DB_MEETING_PARTICIPANTS_TABLE")
    user_story_validations_table: str = Field(default="user_story_validations", alias="DB_USER_STORY_VALIDATIONS_TABLE")

    # Azure Speech Service
    azure_speech_key: str = Field(default="", alias="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(default="southeastasia", alias="AZURE_SPEECH_REGION")

    # Auth
    auth_secret: str = Field(default="dev-change-me-secret", alias="AUTH_SECRET")

    # Frontend base URL (used for invite links)
    frontend_base_url: str = Field(default="http://localhost:5173", alias="FRONTEND_BASE_URL")

    # Speech transcription tuning
    transcription_timeout_seconds: int = Field(default=120, alias="TRANSCRIPTION_TIMEOUT_SECONDS")
    transcription_poll_interval_seconds: float = Field(default=1.2, alias="TRANSCRIPTION_POLL_INTERVAL_SECONDS")

    # Auth Service integration
    auth_service_url: str = Field(default="http://localhost:3001", alias="AUTH_SERVICE_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )


def load_postgres_settings() -> PostgresSettings:
    s = Settings()
    return PostgresSettings(
        host=s.db_host.strip(),
        port=s.db_port,
        user=s.db_user.strip(),
        password=s.db_password.strip(),
        dbname=s.db_name.strip(),
        sslmode=s.db_sslmode.strip(),
        meetings_table=s.meetings_table.strip(),
        chat_messages_table=s.chat_messages_table.strip(),
        transcripts_table=s.transcripts_table.strip(),
        transcript_utterances_table=s.transcript_utterances_table.strip(),
        requirements_table=s.requirements_table.strip(),
        requirement_embeddings_table=s.requirement_embeddings_table.strip(),
        requirement_utterance_mapping_table=s.requirement_utterance_mapping_table.strip(),
        conflicts_table=s.conflicts_table.strip(),
        user_stories_table=s.user_stories_table.strip(),
        user_story_requirement_mapping_table=s.user_story_requirement_mapping_table.strip(),
        acceptance_criteria_table=s.acceptance_criteria_table.strip(),
        meeting_participants_table=s.meeting_participants_table.strip(),
        user_story_validations_table=s.user_story_validations_table.strip(),
    )


def load_speech_settings() -> SpeechServiceSettings:
    s = Settings()
    return SpeechServiceSettings(
        transcription_timeout_seconds=s.transcription_timeout_seconds,
        polling_interval_seconds=s.transcription_poll_interval_seconds,
        cors_origins=[origin.strip() for origin in s.cors_origins.split(",") if origin.strip()],
        auth_secret=s.auth_secret.strip(),
        azure_speech_key=s.azure_speech_key.strip(),
        azure_speech_region=s.azure_speech_region.strip(),
        frontend_base_url=s.frontend_base_url.strip(),
    )
