"""FastAPI application entrypoint for transcript-to-user-stories RAG."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..models.schemas import (
	GenerateStoriesRequest,
	GenerateStoriesResponse,
	IngestResponse,
	PipelineRunRequest,
	PipelineRunResponse,
	Transcript,
)
from ..pipeline.orchestrator import RAGPipeline


app = FastAPI(title="Transcription to User Stories RAG", version="0.1.0")

# Enable CORS for frontend dev server and production origins
app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		"http://localhost:5173",
		"http://127.0.0.1:5173",
		"http://localhost:3000",
		"http://127.0.0.1:3000",
	],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

pipeline = RAGPipeline.from_env()


@app.get("/health")
def health() -> dict[str, str]:
	"""Simple health endpoint."""
	return {"status": "ok"}


@app.post("/ingest-transcript", response_model=IngestResponse)
def ingest_transcript(transcript: Transcript) -> IngestResponse:
	"""Preprocess and chunk transcript without indexing."""
	chunks = pipeline.ingest_transcript(transcript)
	return IngestResponse(transcript_id=transcript.transcript_id, chunk_count=len(chunks), chunks=chunks)


@app.post("/index-transcript")
def index_transcript(transcript: Transcript) -> dict[str, int | str]:
	"""Preprocess, chunk, embed, and index transcript chunks in Chroma."""
	indexed = pipeline.index_transcript(transcript)
	return {"transcript_id": transcript.transcript_id, "indexed_chunks": indexed}


@app.post("/generate-stories", response_model=GenerateStoriesResponse)
def generate_stories(request: GenerateStoriesRequest) -> GenerateStoriesResponse:
	"""Retrieve evidence and generate user stories from indexed chunks."""
	try:
		return pipeline.generate_stories(request)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/pipeline/run", response_model=PipelineRunResponse)
def pipeline_run(request: PipelineRunRequest) -> PipelineRunResponse:
	"""Run full end-to-end pipeline from transcript to validated stories."""
	return pipeline.run(request)
