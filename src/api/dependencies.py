"""API Dependencies shared across routers."""

from __future__ import annotations
from typing import Any
from fastapi import Header, HTTPException, Request

from src.core.config import Settings, SpeechServiceSettings
from src.core.security import decode_jwt
from src.db.postgres import PostgresGateway
from src.repositories.meeting_repository import MeetingRepository
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.repositories.conflict_repository import ConflictRepository
from src.repositories.user_story_repository import UserStoryRepository
from src.services.speech.transcription_service import TranscriptionService
from src.services.speech.azure_client import AzureSpeechClient
from src.services.speech.live_meeting_service import LiveMeetingService
from src.services.speech.websocket_manager import WebSocketManager
from src.services.speech.live_meeting_coordinator import LiveMeetingCoordinator
from src.services.requirement.requirement_extractor import RequirementExtractorService
from src.services.requirement.requirement_thread_service import RequirementThreadService
from src.pipeline.story_pipeline import StoryPipeline
from src.services.generation.user_story_service import UserStoryService


def get_current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")
    
    token = authorization.replace("Bearer ", "")
    settings = Settings()
    
    user = decode_jwt(token, settings.auth_secret)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or token expired")
    return user


# --- Dependency Providers Reading from app.state ---

def get_settings(request: Request) -> Settings:
    return request.app.state.settings

def get_gateway(request: Request) -> PostgresGateway:
    return request.app.state.gateway


def get_speech_settings(request: Request) -> SpeechServiceSettings:
    return request.app.state.speech_settings


def get_azure_speech_client(request: Request) -> AzureSpeechClient:
    return request.app.state.azure_speech


def get_meeting_repo(request: Request) -> MeetingRepository:
    return request.app.state.meeting_repo


def get_requirement_repo(request: Request) -> RequirementRepository:
    return request.app.state.req_repo


def get_transcript_repo(request: Request) -> TranscriptRepository:
    return request.app.state.transcript_repo


def get_conflict_repo(request: Request) -> ConflictRepository:
    return request.app.state.conflict_repo


def get_transcription_service(request: Request) -> TranscriptionService:
    return request.app.state.transcription_service


def get_websocket_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager


def get_requirement_extractor(request: Request) -> RequirementExtractorService:
    return request.app.state.req_extractor


def get_requirement_thread_service(request: Request) -> RequirementThreadService:
    return request.app.state.thread_service


def get_live_meeting_service(request: Request) -> LiveMeetingService:
    return request.app.state.live_meeting_service


def get_live_meeting_coordinator(request: Request) -> LiveMeetingCoordinator:
    return request.app.state.meeting_coordinator


def get_story_pipeline(request: Request) -> StoryPipeline:
    return request.app.state.story_pipeline


def get_user_story_service() -> UserStoryService:
    """Return a shared UserStoryService instance (stateless, safe to construct per-request)."""
    return UserStoryService()

def get_user_story_repo(request: Request) -> UserStoryRepository:
    return request.app.state.story_repo
