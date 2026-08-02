"""Service layer for user story generation from finalized requirements."""

from __future__ import annotations

from fastapi import HTTPException

from src.models.transcript import Chunk
from src.pipeline.story_pipeline import StoryPipeline
from src.services.requirement.requirement_extractor import RequirementExtractorService
from src.repositories.requirement_repository import RequirementRepository
from src.core.logger import get_logger

LOGGER = get_logger(__name__)


def _utterances_to_chunks(utterance_rows: list[dict]) -> list[Chunk]:
    """Convert PostgreSQL transcript_utterances rows into Chunk objects.

    Chunk objects are the expected input format for the ValidationEngine's
    Evidence and Hallucination layers.  Empty utterance texts are skipped.
    """
    chunks = []
    for i, row in enumerate(utterance_rows):
        text = (row.get("utterance_text") or "").strip()
        if not text:
            continue
        chunks.append(Chunk(
            chunk_id=str(row.get("id", f"utt-{i}")),
            transcript_id=str(row.get("transcript_id", "unknown")),
            chunk_index=i,
            text=text,
            speakers=[row["speaker_name"]] if row.get("speaker_name") else [],
            timestamp_start=row.get("start_time"),
            timestamp_end=row.get("end_time"),
            metadata={"utterance_type": row.get("utterance_type") or ""},
        ))
    return chunks


class UserStoryService:
    """Orchestrates user story generation from finalized meeting requirements."""

    def generate_from_requirements(
        self,
        meeting_id: str,
        pipeline: StoryPipeline,
        req_extractor: RequirementExtractorService,
        req_repo: RequirementRepository,
    ) -> dict:
        """Generate agile user stories directly from finalized active requirements.

        All 5 validation layers are active:
          - Layer 1 (Rule)          — always runs
          - Layer 2 (Evidence)      — RAG chunks retrieved from pgvector
          - Layer 3 (Hallucination) — LLM grounding check against RAG chunks
          - Layer 4 (INVEST)        — LLM INVEST scoring
          - Layer 5 (Overall)       — weighted aggregate

        Raises:
            HTTPException: 400 if no active requirements exist for the meeting.
        """
        # --- 1. Fetch active requirements ---
        active_reqs = [
            r
            for r in req_repo.get_all_for_conflict_check(meeting_id)
            if r.get("status") == "active"
        ]

        if not active_reqs:
            raise HTTPException(
                status_code=400,
                detail="No active requirements found. Please review and finalize requirements first.",
            )

        LOGGER.info(
            "[UserStoryService] Found %d active requirement(s) for meeting %s.",
            len(active_reqs),
            meeting_id,
        )

        # --- 2. Retrieve pgvector evidence chunks ---
        evidence_chunks = self._retrieve_evidence(
            meeting_id=meeting_id,
            active_reqs=active_reqs,
            pipeline=pipeline,
            req_extractor=req_extractor,
        )

        # --- 3. Generate stories ---
        batch = pipeline.story_generator.generate_from_requirements(active_reqs)

        # --- 4. Validate ---
        validation_results = pipeline.validation_engine.validate_batch(batch, evidence_chunks)

        for vr in validation_results:
            LOGGER.info(
                "[ValidationSummary] story=%s | rule=%.1f | evidence=%.1f | "
                "semantic=%.4f | invest=%.2f | hallucination=%.4f | overall=%.1f -> %s",
                vr.story_id,
                vr.rule_score,
                vr.evidence_score,
                vr.semantic_similarity,
                vr.invest_score,
                vr.hallucination_score,
                vr.overall_quality_score,
                vr.status,
            )

        all_issues = [issue for vr in validation_results for issue in vr.issues]

        # --- 5. Persist stories, mappings, and validation results ---
        pipeline.story_repo.save(stories=batch.stories, meeting_id=meeting_id)

        mappings = [
            {"user_story_id": story.story_id, "requirement_id": req_id}
            for story in batch.stories
            for req_id in story.evidence_refs
            if any(r["id"] == req_id for r in active_reqs)
        ]
        if mappings:
            pipeline.story_repo.save_requirement_mappings(mappings)

        if validation_results:
            pipeline.validation_repo.save(validation_results)

        # --- 6. Return response ---
        return {
            "status": "success",
            "meeting_id": meeting_id,
            "stories": [s.model_dump() for s in batch.stories],
            "issues": [issue.model_dump() for issue in all_issues],
            "validation_results": [vr.model_dump() for vr in validation_results],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _retrieve_evidence(
        self,
        *,
        meeting_id: str,
        active_reqs: list[dict],
        pipeline: StoryPipeline,
        req_extractor: RequirementExtractorService,
    ) -> list[Chunk]:
        """Compute a combined embedding and retrieve relevant utterance chunks via pgvector.

        Returns an empty list (with a warning) if retrieval fails, so story
        generation can still proceed without evidence.
        """
        combined_query = " ".join(r["requirement_text"] for r in active_reqs[:10])
        try:
            query_embedding = req_extractor.get_embedding(combined_query)
            utterance_rows = pipeline.transcript_repo.find_relevant_utterances(
                query_embedding,
                meeting_id=meeting_id,
                top_k=pipeline.settings.retrieval_top_k,
            )
            chunks = _utterances_to_chunks(utterance_rows)
            LOGGER.info(
                "[UserStoryService] pgvector retrieved %d evidence chunk(s) for meeting %s.",
                len(chunks),
                meeting_id,
            )
            if not chunks:
                LOGGER.warning(
                    "[UserStoryService] No utterance embeddings found for meeting %s.",
                    meeting_id,
                )
            return chunks
        except Exception as exc:
            LOGGER.warning(
                "[UserStoryService] pgvector retrieval failed (%s) — proceeding without evidence.",
                exc,
            )
            return []
