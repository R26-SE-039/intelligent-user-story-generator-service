"""Chroma vector store client with configurable embedding backend."""

from __future__ import annotations

import hashlib
from typing import Any

import chromadb
from openai import OpenAI

from src.core.config import Settings
from src.models.transcript import Chunk

def _hash_embedding(text: str, dim: int = 256) -> list[float]:
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
        
        _is_openai_native = "openai.com" in getattr(settings, "llm_api_base", "")
        self.openai_client = OpenAI(api_key=settings.llm_api_key) if (settings.llm_api_key and _is_openai_native) else None

    def embed(self, text: str) -> list[float]:
        """Generate embedding for the given text."""
        if self.openai_client is None:
            return _hash_embedding(text)
        response = self.openai_client.embeddings.create(
            model=self.settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding
