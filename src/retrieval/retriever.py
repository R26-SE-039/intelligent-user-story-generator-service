"""Retrieve relevant evidence chunks for generation."""

from __future__ import annotations

from ..models.schemas import Chunk
from .chroma_store import ChromaVectorStore


class Retriever:
	"""High-level retrieval facade over the vector store."""

	def __init__(self, vector_store: ChromaVectorStore) -> None:
		self.vector_store = vector_store

	def retrieve(self, query: str, top_k: int, filters: dict | None = None) -> list[Chunk]:
		"""Return top relevant chunks for the query."""
		return self.vector_store.query(query=query, top_k=top_k, filters=filters)
