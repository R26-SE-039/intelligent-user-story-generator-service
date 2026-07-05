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


from pydantic import BaseModel
from src.db.postgres import PostgresGateway
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.user_story_repository import UserStoryRepository
from src.services.generation.story_validator import validate_stories

_gateway = PostgresGateway.from_env()
_req_repo = RequirementRepository(_gateway)
_story_repo = UserStoryRepository(_gateway)

class GenerateFromRequirementsRequest(BaseModel):
    meeting_id: str
    query: str | None = "Generate user stories based on finalized requirements"

@router.post("/generate-from-requirements")
def generate_from_requirements(request: GenerateFromRequirementsRequest):
    """Generate agile user stories directly from finalized active requirements."""
    try:
        # 1. Fetch requirements for this meeting
        requirements = _req_repo.get_all_for_conflict_check(request.meeting_id)
        active_reqs = [r for r in requirements if r["status"] == "active"]
        
        if not active_reqs:
            raise HTTPException(
                status_code=400, 
                detail="No active requirements found. Please review and finalize requirements first."
            )

        # 2. Call StoryGenerator to generate stories from these requirements
        batch = pipeline.story_generator.generate_from_requirements(active_reqs)
        
        # 3. Validate stories
        issues = validate_stories(batch)
        
        # 4. Save stories to database
        if _story_repo is not None:
            _story_repo.save(
                stories=batch.stories,
                meeting_id=request.meeting_id
            )
            
            # 5. Build and save requirement-to-story mappings
            mappings = []
            for story in batch.stories:
                for req_id in story.evidence_refs:
                    # Validate that req_id is a valid UUID/string in active_reqs
                    if any(r["id"] == req_id for r in active_reqs):
                        mappings.append({
                            "user_story_id": story.story_id,
                            "requirement_id": req_id
                        })
            if mappings:
                _story_repo.save_requirement_mappings(mappings)
                
        # 6. Return response matching generation schemas
        return {
            "status": "success",
            "meeting_id": request.meeting_id,
            "stories": [s.model_dump() for s in batch.stories],
            "issues": [issue.model_dump() for issue in issues]
        }
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        print(f"REQUIREMENTS GENERATION CRASH: {str(exc)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Requirements Generation Failed: {str(exc)}"
        )

