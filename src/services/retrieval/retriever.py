"""Retrieve relevant evidence chunks for generation."""

from __future__ import annotations

from src.models.transcript import Chunk
from src.services.retrieval.chroma_service import ChromaService


class Retriever:
    """High-level retrieval facade over the embedding service."""

    def __init__(self, chroma_service: ChromaService) -> None:
        self.chroma_service = chroma_service

    def retrieve(self, query: str, top_k: int, filters: dict | None = None) -> list[Chunk]:
        """Return top relevant chunks for the query."""
        return self.chroma_service.query(query=query, top_k=top_k, filters=filters)
