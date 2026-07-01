"""Service for ChromaDB retrieval logic."""

from __future__ import annotations

from src.repositories.embedding_repository import EmbeddingRepository
from src.models.transcript import Chunk


class ChromaService:
    """Service to handle embedding logic and querying."""

    def __init__(self, repository: EmbeddingRepository) -> None:
        self.repository = repository

    def index_chunks(self, chunks: list[Chunk]) -> None:
        self.repository.upsert(chunks)

    def query(self, query: str, top_k: int, filters: dict | None = None) -> list[Chunk]:
        return self.repository.query(query, top_k, filters)
