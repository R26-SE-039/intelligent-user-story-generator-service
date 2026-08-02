"""Orchestrate ingestion, retrieval, generation, and validation steps."""

from __future__ import annotations

from src.core.config import Settings
from src.core.logger import get_logger
from src.db.chroma import ChromaVectorStore
from src.repositories.embedding_repository import EmbeddingRepository
from src.repositories.user_story_repository import UserStoryRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.repositories.validation_repository import ValidationRepository
from src.services.speech.transcription_service import TranscriptionService
from src.services.retrieval.chroma_service import ChromaService
from src.services.retrieval.retriever import Retriever
from src.services.generation.story_generator import StoryGenerator
from src.services.generation.validation import ValidationEngine
from src.services.requirement.utterance_classifier import UtteranceClassifier
from src.services.requirement.context_builder import ContextBuilder

from src.models.schemas import (
    GenerateStoriesRequest,
    GenerateStoriesResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    Transcript,
)

LOGGER = get_logger(__name__)


class StoryPipeline:
    """Pipeline that performs transcript chunking, retrieval, and story generation."""

    @classmethod
    def from_env(
        cls,
        transcript_repo: "TranscriptRepository | None" = None,
        story_repo: "UserStoryRepository | None" = None,
        validation_repo: "ValidationRepository | None" = None,
    ) -> "StoryPipeline":
        """Instantiate StoryPipeline from environment settings."""
        return cls(
            settings=Settings(),
            transcript_repo=transcript_repo,
            story_repo=story_repo,
            validation_repo=validation_repo,
        )

    def __init__(
        self, 
        settings: Settings, 
        transcript_repo: TranscriptRepository | None = None,
        story_repo: UserStoryRepository | None = None,
        validation_repo: ValidationRepository | None = None,
    ) -> None:
        self.settings = settings
        self.transcript_repo = transcript_repo
        self.story_repo = story_repo
        self.validation_repo = validation_repo
        
        self.vector_store = ChromaVectorStore(settings)
        self.embedding_repo = EmbeddingRepository(self.vector_store)
        self.chroma_service = ChromaService(self.embedding_repo)
        
        self.retriever = Retriever(self.chroma_service)
        self.transcription_service = TranscriptionService()
        self.story_generator = StoryGenerator(
            api_key=settings.llm_api_key,
            api_base=None,
            model=settings.chat_model
        )

        # Validation engine — reuses the same genai client as the RAG pipeline
        self.validation_engine = ValidationEngine(
            genai_client=self.vector_store.genai_client,
            model=settings.chat_model,
        )

        # ModernBERT utterance classifier — loaded once as a singleton
        self.utterance_classifier = UtteranceClassifier()
        self.context_builder = ContextBuilder()


    def ingest_transcript(self, transcript: Transcript):
        """Return processed transcript chunks without indexing."""
        chunks = self.transcription_service.chunk_transcript(
            transcript,
            chunk_size_words=self.settings.chunk_size_words,
            chunk_overlap_words=self.settings.chunk_overlap_words,
        )
        if self.transcript_repo is not None:
            self.transcript_repo.save(transcript)
        return chunks

    def index_transcript(self, transcript: Transcript) -> int:
        """Chunk transcript and upsert chunks into vector store."""
        chunks = self.ingest_transcript(transcript)
        if not chunks:
            return 0
        self.chroma_service.index_chunks(chunks)
        LOGGER.info("Indexed %s chunks for transcript_id=%s", len(chunks), transcript.transcript_id)
        return len(chunks)

    def _generate_stories(
        self,
        request: GenerateStoriesRequest,
        *,
        transcript_id: str | None = None,
        project_id: str | None = None,
    ) -> GenerateStoriesResponse:
        """Retrieve evidence and generate + validate stories."""
        top_k = request.top_k or self.settings.retrieval_top_k
        evidence = self.retriever.retrieve(request.query, top_k=top_k, filters=request.filters)
        if not evidence:
            raise ValueError("No evidence found for query. Index transcripts first or adjust filters.")

        batch = self.story_generator.generate(query=request.query, evidence=evidence)

        # 5-layer validation
        validation_results = self.validation_engine.validate_batch(batch, evidence)

        # Flatten issues from all validation results for the legacy issues field
        all_issues = [issue for vr in validation_results for issue in vr.issues]

        response = GenerateStoriesResponse(
            query=request.query,
            stories=batch.stories,
            issues=all_issues,
            evidence_chunk_ids=[item.chunk_id for item in evidence],
            validation_results=validation_results,
        )
        if self.story_repo is not None:
            self.story_repo.save(
                stories=response.stories,
                meeting_id=transcript_id,
            )

        if self.validation_repo is not None and validation_results:
            self.validation_repo.save(validation_results)
        return response


    def run(self, request: PipelineRunRequest) -> PipelineRunResponse:
        """Run classify + index + retrieve + generate in a single operation."""
        LOGGER.info("--- Starting Pipeline Run for transcript_id=%s ---", request.transcript.transcript_id)

        # Phase 0: ModernBERT Utterance Classification
        LOGGER.info("[Phase 0/4] Running ModernBERT utterance classification...")
        utterance_objs = getattr(request.transcript, "utterances", [])
        utterances = [u.text for u in utterance_objs if hasattr(u, "text")]
        if utterances:
            context_texts = self.context_builder.build_all(utterances)
            classifications = self.utterance_classifier.classify_batch(context_texts)
            for i, result in enumerate(classifications):
                if i < len(utterance_objs):
                    utterance_objs[i].utterance_type = result.label
            requirement_indices = [
                i for i, result in enumerate(classifications)
                if result.is_requirement
            ]
            total = len(utterances)
            found = len(requirement_indices)
            LOGGER.info(
                "[Phase 0/4] Classification complete: %d/%d utterances identified as Requirements.",
                found,
                total,
            )
        else:
            LOGGER.info("[Phase 0/4] No structured utterances found, skipping classification.")

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
            validation_results=generation.validation_results,
        )
