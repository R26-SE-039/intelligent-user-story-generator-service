"""Layer 2 — Evidence Validation via Gemini Embeddings.

Computes the semantic similarity between each generated user story
and the retrieved evidence chunks using Gemini Embeddings
(``models/gemini-embedding-001``), which is the same model already used
by the RAG pipeline.

Cosine similarity workflow:
    Generated story text → Gemini Embedding
    Evidence chunk texts → Gemini Embedding
    cosine_similarity(story_emb, chunk_emb) → max → semantic_similarity (0–1)
    evidence_score = semantic_similarity × 100
"""

from __future__ import annotations

import logging
import math

from google import genai

from src.models.transcript import Chunk

LOGGER = logging.getLogger(__name__)

_EMBEDDING_MODEL = "models/gemini-embedding-001"
_EMBEDDING_DIM = 3072


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _embed(client: genai.Client, text: str) -> list[float]:
    """Embed a single text string with Gemini. Returns zero-vector on failure."""
    if not text:
        return [0.0] * _EMBEDDING_DIM
    try:
        res = client.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=text,
        )
        if res.embeddings and len(res.embeddings) > 0:
            return list(res.embeddings[0].values)
    except Exception as exc:
        LOGGER.warning("[EvidenceValidator] Embedding failed: %s", exc)
    return [0.0] * _EMBEDDING_DIM


class EvidenceValidator:
    """Compare a user story against transcript evidence using Gemini Embeddings.

    This validator is intentionally stateless — a single instance can be
    reused across multiple stories and batches.
    """

    def __init__(self, genai_client: genai.Client) -> None:
        self._client = genai_client

    def validate(self, story_text: str, evidence_chunks: list[Chunk]) -> tuple[float, float]:
        """Return ``(semantic_similarity, evidence_score)``.

        Args:
            story_text: The full user story string.
            evidence_chunks: Retrieved transcript chunks used as grounding.

        Returns:
            A tuple of:
            - ``semantic_similarity`` — max cosine similarity (0.0–1.0)
            - ``evidence_score``  — semantic_similarity × 100 (0.0–100.0)
        """
        if not evidence_chunks or not story_text.strip():
            LOGGER.warning("[EvidenceValidator] No evidence or empty story — returning 0.")
            return 0.0, 0.0

        story_emb = _embed(self._client, story_text)

        # Embed all chunks and track the maximum similarity
        max_similarity = 0.0
        for chunk in evidence_chunks:
            if not chunk.text:
                continue
            chunk_emb = _embed(self._client, chunk.text)
            sim = _cosine_similarity(story_emb, chunk_emb)
            if sim > max_similarity:
                max_similarity = sim

        max_similarity = round(max_similarity, 4)
        evidence_score = round(max_similarity * 100.0, 2)
        LOGGER.debug(
            "[EvidenceValidator] story_len=%d, chunks=%d → semantic_similarity=%.4f",
            len(story_text),
            len(evidence_chunks),
            max_similarity,
        )
        return max_similarity, evidence_score
