"""Orchestrate ingestion, retrieval, generation, and validation steps."""

from __future__ import annotations

import logging

from persistence import TextPersistence
from postgres_gateway import PostgresGateway
from src.core.config import Settings
from src.generation.story_generator import StoryGenerator
from src.ingestion.preprocess import chunk_transcript
from src.models.schemas import (
	GenerateStoriesRequest,
	GenerateStoriesResponse,
	PipelineRunRequest,
	PipelineRunResponse,
	StoryIssue,
	Transcript,
)
from src.retrieval.chroma_store import ChromaVectorStore
from src.retrieval.retriever import Retriever
from src.validation.story_validator import validate_stories

LOGGER = logging.getLogger(__name__)


class RAGPipeline:
	"""Pipeline that performs transcript ingestion, retrieval, and story generation."""

	def __init__(self, settings: Settings, persistence: TextPersistence | None = None) -> None:
		self.settings = settings
		self.persistence = persistence
		self.vector_store = ChromaVectorStore(settings)
		self.retriever = Retriever(self.vector_store)
		self.story_generator = StoryGenerator(settings.llm_api_key, settings.chat_model, settings.llm_api_base)

	@classmethod
	def from_env(cls) -> "RAGPipeline":
		return cls(Settings(), persistence=TextPersistence(PostgresGateway.from_env()))

	def ingest_transcript(self, transcript: Transcript):
		"""Return processed transcript chunks without indexing."""
		chunks = chunk_transcript(
			transcript,
			chunk_size_words=self.settings.chunk_size_words,
			chunk_overlap_words=self.settings.chunk_overlap_words,
		)
		if self.persistence is not None:
			self.persistence.save_transcript(transcript)
		return chunks

	def index_transcript(self, transcript: Transcript) -> int:
		"""Chunk transcript and upsert chunks into vector store."""
		chunks = self.ingest_transcript(transcript)
		if not chunks:
			return 0
		self.vector_store.upsert(chunks)
		LOGGER.info("Indexed %s chunks for transcript_id=%s", len(chunks), transcript.transcript_id)
		return len(chunks)

	def _generate_stories(
		self,
		request: GenerateStoriesRequest,
		*,
		transcript_id: str | None = None,
		project_id: str | None = None,
	) -> GenerateStoriesResponse:
		"""Retrieve evidence and generate validated stories."""
		top_k = request.top_k or self.settings.retrieval_top_k
		evidence = self.retriever.retrieve(request.query, top_k=top_k, filters=request.filters)
		if not evidence:
			raise ValueError("No evidence found for query. Index transcripts first or adjust filters.")

		batch = self.story_generator.generate(query=request.query, evidence=evidence)
		issues = validate_stories(batch)
		response = GenerateStoriesResponse(
			query=request.query,
			stories=batch.stories,
			issues=issues,
			evidence_chunk_ids=[item.chunk_id for item in evidence],
		)
		if self.persistence is not None:
			self.persistence.save_user_stories(
				meeting_id=transcript_id,
				stories=response.stories
			)
		return response

	def generate_stories(self, request: GenerateStoriesRequest) -> GenerateStoriesResponse:
		return self._generate_stories(request)

	def run(self, request: PipelineRunRequest) -> PipelineRunResponse:
		"""Run index + retrieve + generate in a single operation with phase tracking."""
		LOGGER.info("--- Starting Pipeline Run for transcript_id=%s ---", request.transcript.transcript_id)
		
		# Phase 1: Indexing
		LOGGER.info("[Phase 1/4] Chunking and Indexing transcript...")
		indexed_chunks = self.index_transcript(request.transcript)
		
		# Phase 2: Generation
		LOGGER.info("[Phase 2/4] Retrieving context and generating stories via AI...")
		generation = self._generate_stories(
			GenerateStoriesRequest(
				query=request.query,
				top_k=request.top_k,
				filters=request.filters,
			),
			transcript_id=request.transcript.transcript_id,
			project_id=request.transcript.project_id,
		)
		
		LOGGER.info("[Phase 3/4] Stories generated and validated successfully.")
		
		# Phase 4: Finalizing
		LOGGER.info("[Phase 4/4] Pipeline completed for transcript_id=%s", request.transcript.transcript_id)
		
		return PipelineRunResponse(
			transcript_id=request.transcript.transcript_id,
			indexed_chunks=indexed_chunks,
			query=request.query,
			stories=generation.stories,
			issues=generation.issues,
			evidence_chunk_ids=generation.evidence_chunk_ids,
		)
