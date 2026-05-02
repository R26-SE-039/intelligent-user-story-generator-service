"""Pipeline-level tests for the RAG flow."""

from __future__ import annotations

from pathlib import Path

from services.text_to_user_stories.src.core.config import Settings
from services.text_to_user_stories.src.generation.story_generator import StoryGenerator
from services.text_to_user_stories.src.ingestion.preprocess import chunk_transcript
from services.text_to_user_stories.src.models.schemas import Chunk, PipelineRunRequest, Transcript, Utterance
from services.text_to_user_stories.src.pipeline.orchestrator import RAGPipeline
from services.text_to_user_stories.src.retrieval.chroma_store import ChromaVectorStore


def _sample_transcript() -> Transcript:
    return Transcript(
        transcript_id="t-001",
        source="test",
        participants=["PO", "Engineer"],
        product_area="platform",
        utterances=[
            Utterance(speaker="PO", text="We need story generation from transcripts with clear acceptance criteria."),
            Utterance(speaker="Engineer", text="The output must include source evidence references to avoid hallucinations."),
            Utterance(speaker="PO", text="Please mark low-confidence stories for clarification."),
        ],
    )


def _settings(tmp_path: Path, collection: str) -> Settings:
    return Settings(
        llm_api_key=None,
        chroma_persist_directory=tmp_path / "chroma",
        vector_db_collection=collection,
        chunk_size_words=12,
        chunk_overlap_words=4,
        retrieval_top_k=3,
    )


def test_chunking_behavior() -> None:
    transcript = _sample_transcript()
    chunks = chunk_transcript(transcript, chunk_size_words=10, chunk_overlap_words=3)
    assert len(chunks) >= 2
    assert chunks[0].chunk_id.startswith("t-001-chunk-")


def test_retrieval_returns_metadata(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "test_collection_retrieval")
    store = ChromaVectorStore(settings)
    chunks = chunk_transcript(_sample_transcript(), chunk_size_words=20, chunk_overlap_words=4)
    store.upsert(chunks)

    results = store.query("evidence references", top_k=2)
    assert results
    assert results[0].transcript_id == "t-001"
    assert isinstance(results[0].metadata, dict)


def test_generation_output_matches_schema() -> None:
    generator = StoryGenerator(api_key=None, model_name="gpt-4o-mini")
    evidence = [
        Chunk(
            chunk_id="chunk-1",
            transcript_id="t-001",
            chunk_index=0,
            text="PO: We need acceptance criteria and evidence references.",
            speakers=["PO"],
            metadata={},
        )
    ]
    result = generator.generate(query="Create user stories", evidence=evidence)
    assert result.stories
    first = result.stories[0]
    assert first.story.startswith("As a")
    assert first.evidence_refs


def test_pipeline_happy_path(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "test_collection_pipeline")
    pipeline = RAGPipeline(settings)
    transcript = _sample_transcript()

    response = pipeline.run(
        PipelineRunRequest(
            transcript=transcript,
            query="Generate user stories for transcript automation",
            top_k=3,
            filters=None,
        )
    )
    assert response.indexed_chunks > 0
    assert response.stories
