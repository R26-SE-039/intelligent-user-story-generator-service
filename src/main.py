"""Main application entrypoint."""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

from contextlib import asynccontextmanager
from src.api.routes.user_stories import router as user_stories_router
from src.api.routes.speech import router as speech_router
from src.api.routes.jira import router as jira_router
from src.core.config import Settings, load_speech_settings
from src.db.postgres import PostgresGateway
from src.repositories.meeting_repository import MeetingRepository
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.repositories.conflict_repository import ConflictRepository
from src.repositories.user_story_repository import UserStoryRepository
from src.repositories.validation_repository import ValidationRepository
from src.services.speech.transcription_service import TranscriptionService
from src.services.speech.azure_client import AzureSpeechClient
from src.services.speech.live_meeting_service import LiveMeetingService
from src.services.speech.websocket_manager import WebSocketManager
from src.services.speech.live_meeting_coordinator import LiveMeetingCoordinator
from src.services.requirement.requirement_extractor import RequirementExtractorService
from src.services.requirement.requirement_thread_service import RequirementThreadService
from src.services.conflict.conflict_detector import ConflictDetectorService
from src.pipeline.story_pipeline import StoryPipeline

settings = Settings()

# --- Lifespan Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Starting up %s...", settings.app_name)
    
    # 1. Core Gateways & Settings
    gateway = PostgresGateway.from_env()
    speech_settings = load_speech_settings()
    azure_speech = AzureSpeechClient(speech_settings)
    
    # 2. Repositories
    meeting_repo = MeetingRepository(gateway)
    req_repo = RequirementRepository(gateway)
    transcript_repo = TranscriptRepository(gateway)
    conflict_repo = ConflictRepository(gateway)
    story_repo = UserStoryRepository(gateway)
    validation_repo = ValidationRepository(gateway)
    
    # 3. Domain Services
    transcription_service = TranscriptionService()
    ws_manager = WebSocketManager(transcription_service)
    req_extractor = RequirementExtractorService()
    conflict_detector = ConflictDetectorService()
    thread_service = RequirementThreadService(gateway=gateway, settings=settings)
    
    live_meeting_service = LiveMeetingService(
        transcription_service=transcription_service,
        req_extractor=req_extractor,
        req_repo=req_repo,
        conflict_detector=conflict_detector,
        conflict_repo=conflict_repo,
        thread_service=thread_service,
        transcript_repo=transcript_repo,
        meeting_repo=meeting_repo,
    )
    
    meeting_coordinator = LiveMeetingCoordinator(
        ws_manager=ws_manager,
        azure_speech=azure_speech,
        live_meeting_service=live_meeting_service,
        meeting_repo=meeting_repo,
        transcription_service=transcription_service,
    )
    
    story_pipeline = StoryPipeline.from_env(
        transcript_repo=transcript_repo,
        story_repo=story_repo,
        validation_repo=validation_repo,
    )


    # 4. Attach dependencies to app.state
    app.state.gateway = gateway
    app.state.speech_settings = speech_settings
    app.state.azure_speech = azure_speech
    app.state.meeting_repo = meeting_repo
    app.state.req_repo = req_repo
    app.state.transcript_repo = transcript_repo
    app.state.conflict_repo = conflict_repo
    app.state.transcription_service = transcription_service
    app.state.ws_manager = ws_manager
    app.state.req_extractor = req_extractor
    app.state.conflict_detector = conflict_detector
    app.state.thread_service = thread_service
    app.state.live_meeting_service = live_meeting_service
    app.state.meeting_coordinator = meeting_coordinator
    app.state.story_pipeline = story_pipeline
    app.state.story_repo = story_repo
    app.state.settings = settings

    yield

    logging.info("Shutting down %s...", settings.app_name)
    # Add any shutdown logic here

# --- Application Setup ---
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

# --- Middleware Setup ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()] or ["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Routers ---
app.include_router(speech_router, prefix="/api/v1/speech")
app.include_router(user_stories_router, prefix="/api/v1/pipeline")
app.include_router(jira_router, prefix="/api/v1/jira")

# --- Health Check Endpoint ---
@app.get("/health")
def health() -> dict[str, str]:
    """Simple service health endpoint."""
    return {"status": "ok", "service": "intelligent-user-story-generator", "environment": settings.environment}

# --- Server Execution ---
if __name__ == "__main__":
    is_dev = settings.environment == "development"
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=is_dev,
        reload_dirs=["src"] if is_dev else None,
    )
