"""Chroma vector store client with configurable embedding backend."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import chromadb

from src.core.config import Settings
from src.core.llm import get_llm_client
from src.models.transcript import Chunk

LOGGER = logging.getLogger(__name__)


def _hash_embedding(text: str, dim: int = 3072) -> list[float]:
    """Create deterministic embedding for local tests and offline mode."""
    values: list[float] = []
    seed = text.encode("utf-8")
    while len(values) < dim:
        digest = hashlib.sha256(seed).digest()
        for byte in digest:
            values.append((byte / 255.0) * 2.0 - 1.0)
            if len(values) == dim:
                break
        seed = digest
    return values


class ChromaVectorStore:
    """Vector operations client for ChromaDB."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.chroma_persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.settings.chroma_persist_directory))
        self.collection = self.client.get_or_create_collection(name=self.settings.vector_db_collection)
        self.genai_client = get_llm_client(settings)

    def embed(self, text: str) -> list[float]:
        """Generate 3072-dimensional embedding for the given text using Gemini."""
        if not text:
            return _hash_embedding("", dim=3072)
        if self.genai_client is None:
            return _hash_embedding(text, dim=3072)

        try:
            res = self.genai_client.models.embed_content(
                model="models/gemini-embedding-001",
                contents=text,
            )
            if res.embeddings and len(res.embeddings) > 0:
                return list(res.embeddings[0].values)
            return _hash_embedding(text, dim=3072)
        except Exception as e:
            LOGGER.warning("[ChromaVectorStore] Embedding API call failed (%s), using fallback: %s", type(e).__name__, e)
            return _hash_embedding(text, dim=3072)
