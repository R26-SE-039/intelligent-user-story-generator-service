"""API routes for user story generation pipeline."""

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Header
from pydantic import BaseModel

from src.models.schemas import (
    PipelineRunRequest,
    PipelineRunResponse,
)
from src.pipeline.story_pipeline import StoryPipeline
from src.services.speech.transcription_service import TranscriptionService
from src.services.requirement.requirement_extractor import RequirementExtractorService
from src.repositories.requirement_repository import RequirementRepository
from src.services.generation.user_story_service import UserStoryService
from src.api.dependencies import (
    get_story_pipeline,
    get_transcription_service,
    get_requirement_extractor,
    get_requirement_repo,
    get_user_story_service,
    get_current_user,
    get_settings,
    get_meeting_repo,
)
from src.core.config import Settings
from src.repositories.meeting_repository import MeetingRepository
from src.utils.helpers import utc_now
from src.services.auth_client import fetch_active_iteration
from src.core.logger import get_logger

router = APIRouter()
LOGGER = get_logger(__name__)


@router.post("/run", response_model=PipelineRunResponse)
def pipeline_run(
    request: PipelineRunRequest,
    pipeline: StoryPipeline = Depends(get_story_pipeline),
) -> PipelineRunResponse:
    """Run full end-to-end pipeline from transcript to validated stories."""
    try:
        return pipeline.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Pipeline Validation Error: {str(exc)}")
    except Exception as exc:
        LOGGER.exception("PIPELINE CRASH")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline Failed: {type(exc).__name__} - {str(exc)}",
        )


@router.post("/upload", response_model=PipelineRunResponse)
async def pipeline_upload(
    file: UploadFile = File(...),
    query: str = Form("Generate user stories based on this transcript"),
    project_id: str | None = Form(None),
    organization_id: str | None = Form(None),
    pipeline: StoryPipeline = Depends(get_story_pipeline),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    meeting_repo: MeetingRepository = Depends(get_meeting_repo),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(None),
) -> PipelineRunResponse:
    """Upload a raw .txt transcript and run the pipeline."""
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    try:
        content = await file.read()
        text = content.decode("utf-8")

        # Create a real meeting record for this upload
        meeting_id = str(uuid.uuid4())

        # Auto-resolve active iteration (same as meeting create)
        iteration_id = None
        if project_id:
            iteration = await fetch_active_iteration(
                project_id=project_id,
                jwt_token=authorization,
                auth_service_url=settings.auth_service_url,
            )
            iteration_id = iteration["id"] if iteration else None

        # Save virtual meeting to meetings table
        meeting_repo.save_meeting({
            "id": meeting_id,
            "organization_id": user.get("organization_id") or organization_id,
            "project_id": project_id,
            "iteration_id": iteration_id,
            "host_id": user.get("id"),
            "title": f"Uploaded Transcript: {file.filename}",
            "status": "completed",
            "start_time": utc_now(),
            "end_time": utc_now(),
        })

        # Run pipeline with real meeting_id as transcript_id
        transcript_id = meeting_id
        transcript = transcription_service.parse_raw_text(text, transcript_id)
        transcript.project_id = project_id

        request = PipelineRunRequest(transcript=transcript, query=query)
        response = pipeline.run(request)
        # Explicitly surface meeting_id for the Human-in-the-Loop BA review flow
        response.meeting_id = meeting_id
        return response
    except Exception as exc:
        LOGGER.exception("UPLOAD PIPELINE CRASH")
        raise HTTPException(
            status_code=500,
            detail=f"Upload Pipeline Failed: {str(exc)}",
        )


class GenerateFromRequirementsRequest(BaseModel):
    meeting_id: str
    query: str | None = "Generate user stories based on finalized requirements"


@router.post("/generate-from-requirements")
def generate_from_requirements(
    request: GenerateFromRequirementsRequest,
    pipeline: StoryPipeline = Depends(get_story_pipeline),
    req_extractor: RequirementExtractorService = Depends(get_requirement_extractor),
    req_repo: RequirementRepository = Depends(get_requirement_repo),
    user_story_service: UserStoryService = Depends(get_user_story_service),
):
    """Generate agile user stories directly from finalized active requirements.

    All 5 validation layers are active:
      - Layer 1 (Rule)        — always runs
      - Layer 2 (Evidence)    — RAG chunks retrieved from ChromaDB/pgvector
      - Layer 3 (Hallucination) — LLM grounding check against RAG chunks
      - Layer 4 (INVEST)      — LLM INVEST scoring
      - Layer 5 (Overall)     — weighted aggregate
    """
    try:
        return user_story_service.generate_from_requirements(
            meeting_id=request.meeting_id,
            pipeline=pipeline,
            req_extractor=req_extractor,
            req_repo=req_repo,
        )
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        LOGGER.exception("REQUIREMENTS GENERATION CRASH")
        raise HTTPException(
            status_code=500,
            detail=f"Requirements Generation Failed: {str(exc)}",
        )


class UpdateStoryRequest(BaseModel):
    meeting_id: str
    title: str
    story: str
    acceptance_criteria: list[str]
    priority: str = "Should"


@router.post("/user-stories/{story_id}/update")
def update_story_endpoint(
    story_id: str,
    request: UpdateStoryRequest,
    pipeline: StoryPipeline = Depends(get_story_pipeline),
    req_extractor: RequirementExtractorService = Depends(get_requirement_extractor),
    user_story_service: UserStoryService = Depends(get_user_story_service),
):
    """Update a user story and trigger mandatory backend system 5-layer re-validation.

    Validation scores and status cannot be manually altered; they are 100% computed
    by the backend validation engine against meeting evidence.
    """
    try:
        return user_story_service.update_and_revalidate_story(
            story_id=story_id,
            meeting_id=request.meeting_id,
            title=request.title,
            story=request.story,
            acceptance_criteria=request.acceptance_criteria,
            priority=request.priority,
            pipeline=pipeline,
            req_extractor=req_extractor,
        )
    except Exception as exc:
        LOGGER.exception("UPDATE STORY CRASH")
        raise HTTPException(
            status_code=500,
            detail=f"Story Update & Re-Validation Failed: {str(exc)}",
        )


class OverrideStatusRequest(BaseModel):
    meeting_id: str
    status: str
    feedback: str | None = None


@router.post("/user-stories/{story_id}/status")
def override_story_status_endpoint(
    story_id: str,
    request: OverrideStatusRequest,
    pipeline: StoryPipeline = Depends(get_story_pipeline),
    user_story_service: UserStoryService = Depends(get_user_story_service),
):
    """Allow a BA/user to manually Approve, Reject, or Reset story status."""
    try:
        return user_story_service.override_story_status(
            story_id=story_id,
            status=request.status,
            meeting_id=request.meeting_id,
            feedback=request.feedback,
            pipeline=pipeline,
        )
    except Exception as exc:
        LOGGER.exception("STATUS OVERRIDE CRASH")
        raise HTTPException(
            status_code=500,
            detail=f"Status Override Failed: {str(exc)}",
        )


@router.get("/iterations/{iteration_id}/requirements-with-stories")
def get_requirements_with_stories(
    iteration_id: str,
    req_repo: RequirementRepository = Depends(get_requirement_repo),
):
    """Return requirements and their mapped user stories for an iteration.

    Each item in the response pairs one active requirement with the user story
    generated from it, including acceptance criteria.

    Returns:
        {
            "iteration_id": "...",
            "total": <int>,
            "items": [
                {
                    "requirement_id": "...",
                    "requirement_text": "...",
                    "requirement_type": "...",
                    "requirement_status": "active",
                    "requirement_created_at": "...",
                    "meeting_id": "...",
                    "meeting_title": "...",
                    "user_story_id": "...",
                    "user_story_title": "...",
                    "user_story_text": "...",
                    "priority": "...",
                    "user_story_status": "...",
                    "acceptance_criteria": ["..."]
                },
                ...
            ]
        }
    """
    try:
        items = req_repo.get_requirements_with_stories_by_iteration(iteration_id)
        return {
            "iteration_id": iteration_id,
            "total": len(items),
            "items": items,
        }
    except Exception as exc:
        LOGGER.exception("REQUIREMENTS WITH STORIES FETCH CRASH")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch requirements with stories: {str(exc)}",
        )
