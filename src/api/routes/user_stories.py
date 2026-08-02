"""API routes for user story generation pipeline."""

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
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
)
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
    pipeline: StoryPipeline = Depends(get_story_pipeline),
    transcription_service: TranscriptionService = Depends(get_transcription_service),
) -> PipelineRunResponse:
    """Upload a raw .txt transcript and run the pipeline."""
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    try:
        content = await file.read()
        text = content.decode("utf-8")

        transcript_id = f"upload-{uuid.uuid4().hex[:8]}"
        transcript = transcription_service.parse_raw_text(text, transcript_id)
        transcript.project_id = project_id

        request = PipelineRunRequest(transcript=transcript, query=query)
        return pipeline.run(request)
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


