"""API routes for user story generation pipeline."""

import uuid
from fastapi import APIRouter, HTTPException, File, UploadFile, Form

from src.models.schemas import (
    PipelineRunRequest,
    PipelineRunResponse,
)
from src.pipeline.story_pipeline import StoryPipeline
from src.services.speech.transcription_service import TranscriptionService

router = APIRouter()
pipeline = StoryPipeline.from_env()
transcription_service = TranscriptionService()

@router.post("/run", response_model=PipelineRunResponse)
def pipeline_run(request: PipelineRunRequest) -> PipelineRunResponse:
    """Run full end-to-end pipeline from transcript to validated stories."""
    try:
        return pipeline.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Pipeline Validation Error: {str(exc)}")
    except Exception as exc:
        print(f"PIPELINE CRASH: {str(exc)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Pipeline Failed: {type(exc).__name__} - {str(exc)}"
        )

@router.post("/upload", response_model=PipelineRunResponse)
async def pipeline_upload(
    file: UploadFile = File(...),
    query: str = Form("Generate user stories based on this transcript"),
    project_id: str | None = Form(None)
) -> PipelineRunResponse:
    """Upload a raw .txt transcript and run the pipeline."""
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")
    
    try:
        content = await file.read()
        text = content.decode("utf-8")
        
        # Parse raw text into structured Transcript
        transcript_id = f"upload-{uuid.uuid4().hex[:8]}"
        transcript = transcription_service.parse_raw_text(text, transcript_id)
        transcript.project_id = project_id
        
        # Create pipeline request
        request = PipelineRunRequest(
            transcript=transcript,
            query=query
        )
        
        return pipeline.run(request)
    except Exception as exc:
        print(f"UPLOAD PIPELINE CRASH: {str(exc)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Upload Pipeline Failed: {str(exc)}"
        )
