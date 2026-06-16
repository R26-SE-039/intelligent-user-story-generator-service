import uvicorn
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware

from src.models.schemas import (
    PipelineRunRequest,
    PipelineRunResponse,
)
from src.pipeline.orchestrator import RAGPipeline
from src.ingestion.preprocess import parse_raw_text
from src.speech.config import load_speech_settings
from src.speech.routes import build_router as build_speech_router
from src.speech.azure_client import AzureSpeechClient
from src.speech.persistence import SpeechPersistence
from src.speech.session_store import SessionStore
from supabase_gateway import SupabaseGateway
import uuid

app = FastAPI(title="Intelligent User Story Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── RAG Pipeline ────────────────────────────────────────────────
pipeline = RAGPipeline.from_env()

# ── Speech / Meeting Module ─────────────────────────────────────
speech_settings = load_speech_settings()
gateway = SupabaseGateway.from_env()
session_store = SessionStore()
azure_speech = AzureSpeechClient(speech_settings)
speech_persistence = SpeechPersistence(gateway)

app.include_router(
    build_speech_router(
        store=session_store,
        azure_speech=azure_speech,
        persistence=speech_persistence,
        settings=speech_settings,
    ),
    prefix="/speech",
)

# ── Health ──────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, str]:
    """Simple service health endpoint."""
    return {"status": "ok", "service": "intelligent-user-story-generator"}

# ── Pipeline Endpoints ──────────────────────────────────────────
@app.post("/pipeline/run", response_model=PipelineRunResponse)
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

@app.post("/pipeline/upload", response_model=PipelineRunResponse)
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
        transcript = parse_raw_text(text, transcript_id)
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
